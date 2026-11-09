"""MT-15 (0.26): the rolling recent-table list (master-state schema 3).

Covers the master-state schema 3 document (``recent_tables``: most
recent first, capped, {path, at} items with the persisted UTC
timestamp), the schema 1 / schema 2 promotion, the named refusals
(malformed entries, over-limit, unknown fields on the old schemas),
and the ``MasterApp`` behavior (``remember_recent_table`` prepends,
dedupes, caps and persists; ``persist_state`` carries the list).
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from test_native_master_ui import CT_GAMEA, _FakeLister

from ct2trainer.native.master_trainer.master_state import (
    ATTACH_MODE_ASK,
    ATTACH_MODE_AUTO,
    MASTER_STATE_FILENAME,
    MASTER_STATE_SCHEMA,
    RECENT_TABLES_LIMIT,
    MasterState,
    MasterStateRefusal,
    load_master_state,
    master_state_from_bytes,
    master_state_to_bytes,
    save_master_state,
)
from ct2trainer.native.master_trainer.master_ui import MasterApp


def _json(document):
    return json.dumps(document, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _envelope(payload):
    import hashlib
    return json.dumps({"payload": payload,
                       "sha256": hashlib.sha256(_json(payload)).hexdigest()},
                      sort_keys=True, separators=(",", ":")).encode("utf-8")


class RecentStateDocumentTests(unittest.TestCase):
    def test_schema3_round_trip(self):
        # MT-26 (0.34): a consistent schema-8 state carries the folder
        # list (load self-heals an empty list to it, so the roundtrip
        # stays exact).
        state = MasterState(MASTER_STATE_SCHEMA, "/tables",
                            last_table="a.ct", attach_mode=ATTACH_MODE_ASK,
                            recent_tables=(("a.ct", "2026-11-03T10:00:00Z"),
                                           ("b.ct", "2026-11-02T09:30:00Z")),
                            table_folders=("/tables",))
        loaded = master_state_from_bytes(master_state_to_bytes(state))
        self.assertEqual(loaded, state)
        self.assertEqual(loaded.schema, MASTER_STATE_SCHEMA)
        self.assertEqual(loaded.recent_tables, state.recent_tables)

    def test_schema2_promotion_defaults_recent(self):
        raw = _envelope({"schema": 2, "last_folder": "/t",
                         "last_table": "a.ct",
                         "attach_mode": "ask"})
        loaded = master_state_from_bytes(raw)
        self.assertEqual(loaded.schema, MASTER_STATE_SCHEMA)
        # MT-26 (0.34): promotion re-anchors the relative table
        # reference to an absolute table key under the stored folder
        # (same Path join the implementation uses - platform-stable).
        from pathlib import Path
        self.assertEqual(loaded.last_table,
                         str(Path("/t") / "a.ct"))
        self.assertEqual(loaded.attach_mode, ATTACH_MODE_ASK)
        self.assertEqual(loaded.recent_tables, ())
        self.assertEqual(loaded.table_folders, ("/t",))

    def test_schema1_promotion_defaults_everything(self):
        raw = _envelope({"schema": 1, "last_folder": "/t"})
        loaded = master_state_from_bytes(raw)
        self.assertEqual(loaded.schema, MASTER_STATE_SCHEMA)
        self.assertIsNone(loaded.last_table)
        self.assertEqual(loaded.attach_mode, ATTACH_MODE_AUTO)
        self.assertEqual(loaded.recent_tables, ())

    def test_schema2_document_cannot_carry_recent_tables(self):
        # The field is schema-3-only: a schema-2 document with it is a
        # foreign field, refused instead of silently promoted.
        raw = _envelope({"schema": 2, "last_folder": "/t",
                         "recent_tables": []})
        with self.assertRaises(MasterStateRefusal) as ctx:
            master_state_from_bytes(raw)
        self.assertIn("unknown fields", str(ctx.exception))

    def test_malformed_recent_entry_is_refused(self):
        for item in (
                {"path": "", "at": "2026-11-03T10:00:00Z"},
                {"path": "a.ct", "at": "2026-11-03 10:00:00"},
                {"path": "a.ct", "at": "not-a-timestamp"},
                {"path": "a.ct"},
                {"path": "a.ct", "at": "2026-11-03T10:00:00Z",
                 "extra": 1},
                "a.ct",
        ):
            raw = _envelope({"schema": 3, "last_folder": "/t",
                             "recent_tables": [item]})
            with self.assertRaises(MasterStateRefusal,
                                   msg=repr(item)):
                master_state_from_bytes(raw)

    def test_over_the_limit_is_refused(self):
        items = [{"path": f"t{i}.ct", "at": "2026-11-03T10:00:00Z"}
                 for i in range(RECENT_TABLES_LIMIT + 1)]
        raw = _envelope({"schema": 3, "last_folder": "/t",
                         "recent_tables": items})
        with self.assertRaises(MasterStateRefusal):
            master_state_from_bytes(raw)

    def test_recent_tables_at_the_limit_loads(self):
        items = [{"path": f"t{i}.ct", "at": "2026-11-03T10:00:00Z"}
                 for i in range(RECENT_TABLES_LIMIT)]
        loaded = master_state_from_bytes(_envelope(
            {"schema": 3, "last_folder": "/t", "recent_tables": items}))
        self.assertEqual(len(loaded.recent_tables), RECENT_TABLES_LIMIT)


class RecentAppTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.folder = root / "tables"
        self.folder.mkdir()
        self.state_home = root / "state"
        self.state_home.mkdir()
        (self.folder / "a.ct").write_text(CT_GAMEA, encoding="utf-8")
        (self.folder / "b.ct").write_text(CT_GAMEA.replace("GameA", "GameB"),
                                          encoding="utf-8")

    def _app(self):
        return MasterApp(self.folder, state_home=self.state_home,
                         poll_ms=50, lister=_FakeLister(),
                         plan_compiler=lambda e, n: {})

    def _stored(self):
        return load_master_state(self.state_home / MASTER_STATE_FILENAME)

    def test_fresh_app_has_no_recent(self):
        app = self._app()
        self.assertEqual(app.recent_tables, ())

    def test_remember_recent_prepends_and_persists(self):
        app = self._app()
        app.remember_recent_table("a.ct")
        app.remember_recent_table("b.ct")
        self.assertEqual([path for path, _at in app.recent_tables],
                         ["b.ct", "a.ct"])
        self.assertEqual(len(app.recent_tables[0][1]), 20)
        stored = self._stored()
        self.assertEqual(stored.schema, MASTER_STATE_SCHEMA)
        self.assertEqual([path for path, _at in stored.recent_tables],
                         ["b.ct", "a.ct"])

    def test_remember_recent_dedupes_to_the_front(self):
        app = self._app()
        app.remember_recent_table("a.ct")
        app.remember_recent_table("b.ct")
        app.remember_recent_table("a.ct")
        self.assertEqual([path for path, _at in app.recent_tables],
                         ["a.ct", "b.ct"])

    def test_remember_recent_is_capped(self):
        app = self._app()
        app.recent_tables = tuple(
            (f"x{i}.ct", "2026-11-01T00:00:00Z")
            for i in range(RECENT_TABLES_LIMIT + 2))
        app.remember_recent_table("top.ct")
        self.assertEqual(len(app.recent_tables), RECENT_TABLES_LIMIT)
        self.assertEqual(app.recent_tables[0][0], "top.ct")
        # The oldest entries drop off the tail.
        self.assertEqual(app.recent_tables[-1][0], "x8.ct")
        self.assertEqual(self._stored().recent_tables, app.recent_tables)

    def test_remember_recent_ignores_bad_input(self):
        app = self._app()
        app.remember_recent_table("")
        app.remember_recent_table(None)
        self.assertEqual(app.recent_tables, ())

    def test_stored_recent_survives_a_new_app(self):
        app = self._app()
        app.remember_recent_table("a.ct")
        app2 = self._app()
        self.assertEqual([path for path, _at in app2.recent_tables],
                         ["a.ct"])


if __name__ == "__main__":
    unittest.main()
