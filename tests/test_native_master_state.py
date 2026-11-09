"""Master state document (MT: ask on first start; 0.25 preferences).

Covers the ``master_state`` persistence module end-to-end: canonical
byte-stable serialization, strict checksum-bound load, every fail-closed
refusal (malformed JSON, invalid shape, tampered checksum, foreign schema,
unknown fields, out-of-bounds last_folder, size limit), tolerant
``load_master_state`` (absent / refused -> None), and
``save_master_state`` directory creation.  Schema 8 (0.34) carries the
MT-10/11/15/16/18/23/25/26 preferences (last_table, attach_mode,
recent_tables, waiting-view settings, pinned tables, status-filter
mode, auto-rescan flag, the indexed table folder list); the table
references are table keys (absolute in a multi-root session, relative
in a single-root one); schema-1/2/3/4/5/6/7 documents are promoted on
load with the documented defaults (the relative references re-anchored
to absolute table keys under the stored last_folder).
"""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from ct2trainer.native.master_trainer.master_state import (
    ATTACH_MODE_ASK,
    ATTACH_MODE_AUTO,
    MASTER_STATE_FILENAME,
    MASTER_STATE_SCHEMA,
    MAX_MASTER_STATE_BYTES,
    MasterState,
    MasterStateRefusal,
    empty_master_state,
    load_master_state,
    master_state_from_bytes,
    master_state_to_bytes,
    save_master_state,
)


def _state(last_folder=None):
    # MT-26 (0.34): a consistent schema-8 state carries the folder
    # list (the single last_folder when one is set) - load self-heals
    # an empty list to the same value, so the roundtrip stays exact.
    return MasterState(schema=MASTER_STATE_SCHEMA, last_folder=last_folder,
                       table_folders=(last_folder,) if last_folder else ())


class MasterStateSerializeTests(unittest.TestCase):
    def test_empty_state_roundtrip(self):
        raw = master_state_to_bytes(empty_master_state())
        document = json.loads(raw)
        self.assertEqual(set(document), {"payload", "sha256"})
        self.assertEqual(document["payload"],
                         {"schema": MASTER_STATE_SCHEMA, "last_folder": None,
                          "last_table": None,
                          "attach_mode": ATTACH_MODE_AUTO,
                          "recent_tables": [],
                          "view_filter": "",
                          "view_sort": "name",
                          "view_mode": "list",
                          "pinned_tables": [],
                          "view_status": "",
                          "auto_rescan": True,
                          "table_folders": []})
        canonical = json.dumps(document["payload"], sort_keys=True,
                               separators=(",", ":"), allow_nan=False,
                               ensure_ascii=True).encode("utf-8")
        self.assertEqual(hashlib.sha256(canonical).hexdigest(),
                         document["sha256"])
        self.assertEqual(master_state_from_bytes(raw), empty_master_state())

    def test_state_with_folder_roundtrip(self):
        folder = "C:\\tables"
        raw = master_state_to_bytes(_state(folder))
        self.assertEqual(master_state_from_bytes(raw), _state(folder))
        # The document is byte-stable: same input, same bytes.
        self.assertEqual(master_state_to_bytes(_state(folder)), raw)
        # Canonical trailing newline (same discipline as the tables index).
        self.assertTrue(raw.endswith(b"\n"))

    # -- schema 2 (0.25) preferences -------------------------------------------

    @staticmethod
    def _document(payload):
        """One checksum-bound document envelope around a raw payload."""
        canonical = json.dumps(payload, sort_keys=True,
                               separators=(",", ":"), allow_nan=False,
                               ensure_ascii=True).encode("utf-8")
        return (json.dumps({"payload": payload,
                            "sha256": hashlib.sha256(canonical).hexdigest()})
                .encode("utf-8"))

    def test_state_with_preferences_roundtrip(self):
        state = MasterState(MASTER_STATE_SCHEMA, "C:\\tables",
                            last_table="sub\\gamea.ct",
                            attach_mode=ATTACH_MODE_ASK,
                            table_folders=("C:\\tables",))
        raw = master_state_to_bytes(state)
        self.assertEqual(master_state_from_bytes(raw), state)

    def test_legacy_schema1_document_promotes_on_load(self):
        payload = {"schema": 1, "last_folder": "C:\\tables"}
        state = master_state_from_bytes(self._document(payload))
        # MT-26 (0.34): promotion fills the folder list with the single
        # stored last folder.
        self.assertEqual(state, MasterState(
            MASTER_STATE_SCHEMA, "C:\\tables", last_table=None,
            attach_mode=ATTACH_MODE_AUTO,
            table_folders=("C:\\tables",)))

    def test_to_bytes_refuses_legacy_schema(self):
        with self.assertRaises(MasterStateRefusal) as ctx:
            master_state_to_bytes(MasterState(schema=1, last_folder=None))
        self.assertIn("schema", str(ctx.exception))

    def test_from_bytes_refuses_bad_attach_mode(self):
        payload = {"schema": MASTER_STATE_SCHEMA, "last_folder": None,
                   "last_table": None, "attach_mode": "sometimes"}
        with self.assertRaises(MasterStateRefusal) as ctx:
            master_state_from_bytes(self._document(payload))
        self.assertIn("attach_mode", str(ctx.exception))

    def test_from_bytes_refuses_malformed_last_table(self):
        for bad in (123, "", ["a.ct"], {"t": 1}):
            payload = {"schema": MASTER_STATE_SCHEMA, "last_folder": None,
                       "last_table": bad, "attach_mode": ATTACH_MODE_AUTO}
            with self.assertRaises(MasterStateRefusal) as ctx:
                master_state_from_bytes(self._document(payload))
            self.assertIn("last_table", str(ctx.exception))

    def test_from_bytes_refuses_oversized_last_table(self):
        # MT-26 (0.34): table references may be absolute table keys, so
        # the length bound is the folder+table bound (8200).
        payload = {"schema": MASTER_STATE_SCHEMA, "last_folder": None,
                   "last_table": "x" * 9000,
                   "attach_mode": ATTACH_MODE_AUTO}
        with self.assertRaises(MasterStateRefusal) as ctx:
            master_state_from_bytes(self._document(payload))
        self.assertIn("last_table", str(ctx.exception))

    def test_from_bytes_refuses_schema1_with_schema2_fields(self):
        payload = {"schema": 1, "last_folder": None, "last_table": "a.ct"}
        with self.assertRaises(MasterStateRefusal) as ctx:
            master_state_from_bytes(self._document(payload))
        self.assertIn("unknown fields", str(ctx.exception))

    def test_to_bytes_refuses_non_state_document(self):
        with self.assertRaises(MasterStateRefusal):
            master_state_to_bytes({"schema": 1, "last_folder": None})

    def test_to_bytes_refuses_foreign_schema(self):
        with self.assertRaises(MasterStateRefusal) as ctx:
            master_state_to_bytes(MasterState(schema=99, last_folder=None))
        self.assertIn("schema", str(ctx.exception))

    def test_to_bytes_refuses_out_of_bounds_folder(self):
        with self.assertRaises(MasterStateRefusal):
            master_state_to_bytes(_state("x" * 5000))

    def test_from_bytes_refuses_malformed_json(self):
        with self.assertRaises(MasterStateRefusal) as ctx:
            master_state_from_bytes(b"not json at all")
        self.assertIn("not valid JSON", str(ctx.exception))

    def test_from_bytes_refuses_invalid_shape(self):
        with self.assertRaises(MasterStateRefusal):
            master_state_from_bytes(b'{"payload": {}}')
        with self.assertRaises(MasterStateRefusal):
            master_state_from_bytes(b'{"payload": {}, "sha256": "x", "extra": 1}')
        with self.assertRaises(MasterStateRefusal):
            master_state_from_bytes(b'{"sha256": "x"}')

    def test_from_bytes_refuses_tampered_checksum(self):
        raw = json.loads(master_state_to_bytes(_state("C:\\t")))
        raw["payload"]["last_folder"] = "C:\\other"
        with self.assertRaises(MasterStateRefusal) as ctx:
            master_state_from_bytes(json.dumps(raw, sort_keys=True)
                                    .encode("utf-8"))
        self.assertIn("checksum does not match", str(ctx.exception))

    def test_from_bytes_refuses_foreign_schema(self):
        payload = {"schema": MASTER_STATE_SCHEMA + 1, "last_folder": None}
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                               allow_nan=False,
                               ensure_ascii=True).encode("utf-8")
        document = {"payload": payload,
                    "sha256": hashlib.sha256(canonical).hexdigest()}
        with self.assertRaises(MasterStateRefusal) as ctx:
            master_state_from_bytes(json.dumps(document).encode("utf-8"))
        self.assertIn("schema", str(ctx.exception))

    def test_from_bytes_refuses_unknown_fields(self):
        payload = {"schema": MASTER_STATE_SCHEMA, "last_folder": None,
                   "surprise": True}
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                               allow_nan=False,
                               ensure_ascii=True).encode("utf-8")
        document = {"payload": payload,
                    "sha256": hashlib.sha256(canonical).hexdigest()}
        with self.assertRaises(MasterStateRefusal) as ctx:
            master_state_from_bytes(json.dumps(document).encode("utf-8"))
        self.assertIn("unknown fields", str(ctx.exception))
        self.assertEqual(ctx.exception.reasons[0].count("surprise"), 1)

    def test_from_bytes_refuses_malformed_last_folder(self):
        for bad in (123, "", ["C:\\t"], {"p": 1}):
            payload = {"schema": MASTER_STATE_SCHEMA, "last_folder": bad}
            canonical = json.dumps(payload, sort_keys=True,
                                   separators=(",", ":"), allow_nan=False,
                                   ensure_ascii=True).encode("utf-8")
            document = {"payload": payload,
                        "sha256": hashlib.sha256(canonical).hexdigest()}
            with self.assertRaises(MasterStateRefusal) as ctx:
                master_state_from_bytes(json.dumps(document).encode("utf-8"))
            self.assertIn("last_folder", str(ctx.exception))

    def test_from_bytes_refuses_oversized_document(self):
        with self.assertRaises(MasterStateRefusal) as ctx:
            master_state_from_bytes(b"x" * (MAX_MASTER_STATE_BYTES + 1))
        self.assertIn("size limit", str(ctx.exception))

    # -- schema 4 (0.27) waiting-view settings (MT-16) ----------------------

    def test_view_settings_roundtrip(self):
        state = MasterState(MASTER_STATE_SCHEMA, "C:\\tables",
                            view_filter="fallout", view_sort="process",
                            view_mode="process",
                            table_folders=("C:\\tables",))
        raw = master_state_to_bytes(state)
        self.assertEqual(master_state_from_bytes(raw), state)

    def test_schema3_document_promotes_on_load(self):
        payload = {"schema": 3, "last_folder": "C:\\tables",
                   "last_table": "sub\\gamea.ct",
                   "attach_mode": ATTACH_MODE_ASK,
                   "recent_tables": [{"path": "sub\\gamea.ct",
                                      "at": "2026-11-03T12:00:00Z"}]}
        state = master_state_from_bytes(self._document(payload))
        self.assertEqual(state.schema, MASTER_STATE_SCHEMA)
        self.assertEqual(state.view_filter, "")
        self.assertEqual(state.view_sort, "name")
        self.assertEqual(state.view_mode, "list")
        # MT-26 (0.34): promotion re-anchors the relative table
        # references to absolute table keys under the stored
        # last_folder (and fills the folder list with that folder).
        from pathlib import Path
        anchored = str(Path("C:\\tables") / "sub\\gamea.ct")
        self.assertEqual(state.last_table, anchored)
        self.assertEqual(state.recent_tables,
                         ((anchored, "2026-11-03T12:00:00Z"),))
        self.assertEqual(state.table_folders, ("C:\\tables",))

    def test_from_bytes_refuses_schema3_with_view_fields(self):
        for field in ("view_filter", "view_sort", "view_mode"):
            payload = {"schema": 3, "last_folder": None,
                       field: "x" if field == "view_filter" else "name"}
            with self.assertRaises(MasterStateRefusal) as ctx:
                master_state_from_bytes(self._document(payload))
            self.assertIn("unknown fields", str(ctx.exception))
            self.assertIn(field, str(ctx.exception))

    def test_from_bytes_refuses_bad_view_settings(self):
        base = {"schema": MASTER_STATE_SCHEMA, "last_folder": None}
        bad_view_sort = dict(base, view_sort="alphabetical")
        with self.assertRaises(MasterStateRefusal) as ctx:
            master_state_from_bytes(self._document(bad_view_sort))
        self.assertIn("view_sort", str(ctx.exception))
        bad_view_mode = dict(base, view_mode="grid")
        with self.assertRaises(MasterStateRefusal) as ctx:
            master_state_from_bytes(self._document(bad_view_mode))
        self.assertIn("view_mode", str(ctx.exception))
        long_filter = dict(base, view_filter="x" * 201)
        with self.assertRaises(MasterStateRefusal) as ctx:
            master_state_from_bytes(self._document(long_filter))
        self.assertIn("view_filter", str(ctx.exception))
        not_a_string = dict(base, view_filter=7)
        with self.assertRaises(MasterStateRefusal) as ctx:
            master_state_from_bytes(self._document(not_a_string))
        self.assertIn("view_filter", str(ctx.exception))

    # -- schema 5 (0.28) pinned tables (MT-18) ----------------------------------

    def test_pinned_tables_roundtrip(self):
        state = MasterState(MASTER_STATE_SCHEMA, "C:\\tables",
                            pinned_tables=("sub\\zeta.ct", "alpha.ct"),
                            table_folders=("C:\\tables",))
        raw = master_state_to_bytes(state)
        self.assertEqual(master_state_from_bytes(raw), state)

    def test_schema4_document_promotes_on_load(self):
        payload = {"schema": 4, "last_folder": "C:\\tables",
                   "last_table": "sub\\gamea.ct",
                   "attach_mode": ATTACH_MODE_ASK,
                   "recent_tables": [{"path": "sub\\gamea.ct",
                                      "at": "2026-11-03T12:00:00Z"}],
                   "view_filter": "", "view_sort": "name",
                   "view_mode": "list"}
        state = master_state_from_bytes(self._document(payload))
        self.assertEqual(state.schema, MASTER_STATE_SCHEMA)
        self.assertEqual(state.pinned_tables, ())
        self.assertEqual(state.table_folders, ("C:\\tables",))

    def test_from_bytes_refuses_schema4_with_pinned_field(self):
        payload = {"schema": 4, "last_folder": None,
                   "pinned_tables": ["sub\\gamea.ct"]}
        with self.assertRaises(MasterStateRefusal) as ctx:
            master_state_from_bytes(self._document(payload))
        self.assertIn("unknown fields", str(ctx.exception))
        self.assertIn("pinned_tables", str(ctx.exception))

    def test_from_bytes_refuses_bad_pinned_tables(self):
        base = {"schema": MASTER_STATE_SCHEMA, "last_folder": None}
        not_a_list = dict(base, pinned_tables="sub\\gamea.ct")
        with self.assertRaises(MasterStateRefusal) as ctx:
            master_state_from_bytes(self._document(not_a_list))
        self.assertIn("pinned_tables", str(ctx.exception))
        bad_item = dict(base, pinned_tables=[7])
        with self.assertRaises(MasterStateRefusal) as ctx:
            master_state_from_bytes(self._document(bad_item))
        self.assertIn("malformed", str(ctx.exception))
        empty_item = dict(base, pinned_tables=[""])
        with self.assertRaises(MasterStateRefusal) as ctx:
            master_state_from_bytes(self._document(empty_item))
        self.assertIn("malformed", str(ctx.exception))
        long_item = dict(base, pinned_tables=["x" * 9000])
        with self.assertRaises(MasterStateRefusal) as ctx:
            master_state_from_bytes(self._document(long_item))
        self.assertIn("malformed", str(ctx.exception))
        over_cap = dict(base,
                        pinned_tables=["t%02d.ct" % i for i in range(26)])
        with self.assertRaises(MasterStateRefusal) as ctx:
            master_state_from_bytes(self._document(over_cap))
        self.assertIn("limit", str(ctx.exception))

    # -- schema 6 (0.31) status filter (MT-23) ----------------------------------

    def test_view_status_roundtrip(self):
        state = MasterState(MASTER_STATE_SCHEMA, "C:\\tables",
                            view_status="attention",
                            table_folders=("C:\\tables",))
        raw = master_state_to_bytes(state)
        self.assertEqual(master_state_from_bytes(raw), state)

    def test_schema5_document_promotes_on_load(self):
        payload = {"schema": 5, "last_folder": "C:\\tables",
                   "last_table": "sub\\gamea.ct",
                   "attach_mode": ATTACH_MODE_ASK,
                   "recent_tables": [{"path": "sub\\gamea.ct",
                                      "at": "2026-11-03T12:00:00Z"}],
                   "view_filter": "", "view_sort": "name",
                   "view_mode": "list",
                   "pinned_tables": ["sub\\gamea.ct"]}
        state = master_state_from_bytes(self._document(payload))
        self.assertEqual(state.schema, MASTER_STATE_SCHEMA)
        self.assertEqual(state.view_status, "")
        # MT-26 (0.34): the persisted pins are re-anchored to absolute
        # table keys under the stored last folder on promotion.
        from pathlib import Path
        self.assertEqual(state.pinned_tables,
                         (str(Path("C:\\tables") / "sub\\gamea.ct"),))
        self.assertEqual(state.table_folders, ("C:\\tables",))

    def test_from_bytes_refuses_schema5_with_status_field(self):
        payload = {"schema": 5, "last_folder": None,
                   "view_status": "ok"}
        with self.assertRaises(MasterStateRefusal) as ctx:
            master_state_from_bytes(self._document(payload))
        self.assertIn("unknown fields", str(ctx.exception))
        self.assertIn("view_status", str(ctx.exception))

    def test_from_bytes_refuses_bad_view_status(self):
        base = {"schema": MASTER_STATE_SCHEMA, "last_folder": None}
        for bad in ("all", "OK", 7, None, ["ok"]):
            with self.assertRaises(MasterStateRefusal) as ctx:
                master_state_from_bytes(
                    self._document(dict(base, view_status=bad)))
            self.assertIn("view_status", str(ctx.exception))

    # -- schema 7 (0.33) auto-rescan flag (MT-25) --------------------------------

    def test_auto_rescan_roundtrip(self):
        state = MasterState(MASTER_STATE_SCHEMA, "C:\\tables",
                            auto_rescan=False,
                            table_folders=("C:\\tables",))
        raw = master_state_to_bytes(state)
        self.assertEqual(master_state_from_bytes(raw), state)
        # The document is byte-stable: same input, same bytes.
        self.assertEqual(master_state_to_bytes(state), raw)

    def test_schema6_document_promotes_on_load(self):
        payload = {"schema": 6, "last_folder": "C:\\tables",
                   "last_table": "sub\\gamea.ct",
                   "attach_mode": ATTACH_MODE_ASK,
                   "recent_tables": [{"path": "sub\\gamea.ct",
                                      "at": "2026-11-08T12:00:00Z"}],
                   "view_filter": "", "view_sort": "name",
                   "view_mode": "list",
                   "pinned_tables": ["sub\\gamea.ct"],
                   "view_status": "ok"}
        state = master_state_from_bytes(self._document(payload))
        self.assertEqual(state.schema, MASTER_STATE_SCHEMA)
        self.assertTrue(state.auto_rescan)
        self.assertEqual(state.view_status, "ok")
        # MT-26 (0.34): the relative references are re-anchored under
        # the stored last folder on promotion.
        from pathlib import Path
        self.assertEqual(state.pinned_tables,
                         (str(Path("C:\\tables") / "sub\\gamea.ct"),))
        self.assertEqual(state.table_folders, ("C:\\tables",))

    def test_from_bytes_refuses_schema6_with_auto_rescan_field(self):
        payload = {"schema": 6, "last_folder": None,
                   "view_status": "ok", "auto_rescan": False}
        with self.assertRaises(MasterStateRefusal) as ctx:
            master_state_from_bytes(self._document(payload))
        self.assertIn("unknown fields", str(ctx.exception))
        self.assertIn("auto_rescan", str(ctx.exception))

    def test_from_bytes_refuses_bad_auto_rescan(self):
        base = {"schema": MASTER_STATE_SCHEMA, "last_folder": None}
        for bad in ("on", "off", 1, 0, None, [True]):
            with self.assertRaises(MasterStateRefusal) as ctx:
                master_state_from_bytes(
                    self._document(dict(base, auto_rescan=bad)))
            self.assertIn("auto_rescan", str(ctx.exception))

    # -- schema 8 (0.34) table folders (MT-26) --------------------------------

    def test_table_folders_roundtrip(self):
        state = MasterState(MASTER_STATE_SCHEMA, "C:\\tables",
                            table_folders=("C:\\tables", "D:\\more"))
        raw = master_state_to_bytes(state)
        self.assertEqual(master_state_from_bytes(raw), state)

    def test_schema7_document_promotes_on_load(self):
        payload = {"schema": 7, "last_folder": "C:\\tables",
                   "last_table": "sub\\gamea.ct",
                   "attach_mode": ATTACH_MODE_ASK,
                   "recent_tables": [{"path": "sub\\gamea.ct",
                                      "at": "2026-11-08T12:00:00Z"}],
                   "view_filter": "", "view_sort": "name",
                   "view_mode": "list",
                   "pinned_tables": ["sub\\gamea.ct"],
                   "view_status": "ok",
                   "auto_rescan": True}
        state = master_state_from_bytes(self._document(payload))
        self.assertEqual(state.schema, MASTER_STATE_SCHEMA)
        # MT-26 (0.34): the folder list is filled from the single stored
        # last folder; the relative table references are re-anchored to
        # absolute table keys under it, so pins / recents / last table
        # survive the upgrade.
        from pathlib import Path
        anchored = str(Path("C:\\tables") / "sub\\gamea.ct")
        self.assertEqual(state.table_folders, ("C:\\tables",))
        self.assertEqual(state.last_table, anchored)
        self.assertEqual(state.recent_tables,
                         ((anchored, "2026-11-08T12:00:00Z"),))
        self.assertEqual(state.pinned_tables, (anchored,))

    def test_schema7_promotion_without_last_folder_keeps_relative_refs(self):
        payload = {"schema": 7, "last_folder": None,
                   "last_table": "sub\\gamea.ct",
                   "attach_mode": ATTACH_MODE_ASK,
                   "recent_tables": [], "view_filter": "",
                   "view_sort": "name", "view_mode": "list",
                   "pinned_tables": [], "view_status": "",
                   "auto_rescan": True}
        state = master_state_from_bytes(self._document(payload))
        self.assertEqual(state.table_folders, ())
        self.assertEqual(state.last_table, "sub\\gamea.ct")

    def test_from_bytes_refuses_schema7_with_table_folders_field(self):
        payload = {"schema": 7, "last_folder": None,
                   "table_folders": ["C:\\tables"]}
        with self.assertRaises(MasterStateRefusal) as ctx:
            master_state_from_bytes(self._document(payload))
        self.assertIn("unknown fields", str(ctx.exception))
        self.assertIn("table_folders", str(ctx.exception))

    def test_from_bytes_refuses_bad_table_folders(self):
        base = {"schema": MASTER_STATE_SCHEMA, "last_folder": None}
        not_a_list = dict(base, table_folders="C:\\tables")
        with self.assertRaises(MasterStateRefusal) as ctx:
            master_state_from_bytes(self._document(not_a_list))
        self.assertIn("table_folders", str(ctx.exception))
        empty_item = dict(base, table_folders=[""])
        with self.assertRaises(MasterStateRefusal) as ctx:
            master_state_from_bytes(self._document(empty_item))
        self.assertIn("table_folders", str(ctx.exception))
        long_item = dict(base, table_folders=["x" * 5000])
        with self.assertRaises(MasterStateRefusal) as ctx:
            master_state_from_bytes(self._document(long_item))
        self.assertIn("table_folders", str(ctx.exception))
        duplicate = dict(base, table_folders=["C:\\tables", "c:\\tables"])
        with self.assertRaises(MasterStateRefusal) as ctx:
            master_state_from_bytes(self._document(duplicate))
        self.assertIn("duplicate", str(ctx.exception))
        from ct2trainer.native.master_trainer.master_state import (
            TABLE_FOLDERS_LIMIT)
        over_cap = dict(base, table_folders=[
            "C:\\t%02d" % i for i in range(TABLE_FOLDERS_LIMIT + 1)])
        with self.assertRaises(MasterStateRefusal) as ctx:
            master_state_from_bytes(self._document(over_cap))
        self.assertIn("limit", str(ctx.exception))

    def test_schema8_empty_folders_self_heal_to_last_folder(self):
        # A schema-8 document with a set last folder but an empty folder
        # list is inconsistent; it self-heals to the single folder
        # (never dropped) instead of losing the user's table roots.
        payload = {"schema": MASTER_STATE_SCHEMA, "last_folder": "C:\\tables",
                   "table_folders": []}
        state = master_state_from_bytes(self._document(payload))
        self.assertEqual(state.table_folders, ("C:\\tables",))

    def test_schema8_empty_folders_without_last_folder_stay_empty(self):
        payload = {"schema": MASTER_STATE_SCHEMA, "last_folder": None,
                   "table_folders": []}
        state = master_state_from_bytes(self._document(payload))
        self.assertEqual(state.table_folders, ())


class MasterStateFileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(self._rmtree)

    def _rmtree(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_save_creates_parent_and_roundtrips(self):
        path = self.tmp / "nested" / "home" / MASTER_STATE_FILENAME
        save_master_state(_state("C:\\tables"), path)
        self.assertTrue(path.is_file())
        self.assertEqual(load_master_state(path), _state("C:\\tables"))

    def test_load_absent_file_is_none(self):
        self.assertIsNone(load_master_state(self.tmp / "missing"
                                             / MASTER_STATE_FILENAME))

    def test_load_refused_file_is_none(self):
        path = self.tmp / MASTER_STATE_FILENAME
        path.write_bytes(b"corrupted")
        self.assertIsNone(load_master_state(path))
        # The corrupted document stays on disk untouched (never a silent
        # reset; the caller falls back to a fresh first start).
        self.assertEqual(path.read_bytes(), b"corrupted")


if __name__ == "__main__":
    unittest.main()
