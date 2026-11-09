"""Master Trainer 0.34: multi-root table index (MT-26).

Covers the multi-root surface of the Master Trainer: the ordered
``RootIndexSet`` (per-root indexes in user order, add / remove /
move-front, the merged lookups with the first-root-wins rule, the
absolute table key as the global identity and the relative-path
fallback), the ``MasterApp`` folder lifecycle (``add_folder`` /
``remove_folder`` / ``move_folder_front`` / ``set_folder`` replace-all,
the persisted folder list in master-state schema 8, the schema-2 index
set round trip, the per-root incremental reconcile), the key-based
explicit load paths (``request_load`` / ``choose`` across roots), the
waiting-view Folder column and row-key resolution, the folder manager
window (primary marker, the add / set-primary / remove wiring), the
table load picker disambiguation, the ``run_master`` multi-root folder
resolution and the auto-rescan over every indexed root.  The
deterministic tests use fake plan compilers; no real process is
attached.
"""
from __future__ import annotations

import hashlib
import io
import json
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from contextlib import redirect_stdout

try:
    import tkinter as tk
except ImportError:  # pragma: no cover - environment without Tcl/Tk
    tk = None

from test_native_master_ui import (CT_GAMEA, CT_GAMEB, _FakeLister,
                                   _all_widgets)

from native_tk_teardown import force_root_release

from ct2trainer.native.master_trainer import master_ui
from ct2trainer.native.master_trainer.analysis_worker import AnalysisWorker
from ct2trainer.native.master_trainer.master_state import (
    MASTER_STATE_FILENAME, MASTER_STATE_SCHEMA, MasterState,
    load_master_state, save_master_state)
from ct2trainer.native.master_trainer.master_ui import (
    AUTO_RESCAN_INTERVAL_SECONDS, MasterApp, MasterWindow, run_master)
from ct2trainer.native.master_trainer.orchestrator import (
    ExplicitLoadRefusal, PendingChoice, STATE_CHOOSING)
from ct2trainer.native.master_trainer.process_watch import (
    ProcessSnapshotEntry)
from ct2trainer.native.master_trainer.table_index import (
    INDEX_SET_SCHEMA, RootIndexSet, TableEntry, TableIndex,
    load_index_set, table_key)


def _plan(sha: str) -> dict:
    """One deterministic plan (the worker cross-checks the table
    content sha inside it)."""
    return {"schema": 2, "table_sha256": sha, "entries": [
        {"id": 1, "supported": True, "kind": "value", "reason": ""},
    ]}


def _entry(rel: str, root: str, names=("GameA.exe",),
           sha="a" * 64) -> TableEntry:
    return TableEntry(rel, 10, 0, sha, names, "ok", None, root=root)


class RootIndexSetTests(unittest.TestCase):
    """The ordered set of per-root indexes (pure, no Tk)."""

    def test_roots_and_index_for_root(self):
        a = TableIndex("C:\\A", {"a.ct": _entry("a.ct", "C:\\A")})
        b = TableIndex("C:\\B", {"b.ct": _entry("b.ct", "C:\\B")})
        s = RootIndexSet([a, b])
        self.assertEqual(s.roots(), ["C:\\A", "C:\\B"])
        self.assertIs(s.index_for_root("c:\\a"), a)
        self.assertIsNone(s.index_for_root("C:\\C"))
        self.assertEqual(RootIndexSet().roots(), [])
        self.assertEqual(RootIndexSet().root, "")

    def test_add_root_appends_and_refuses_duplicates(self):
        s = RootIndexSet([TableIndex("C:\\A", {})])
        self.assertTrue(s.add_root(TableIndex("C:\\B", {})))
        self.assertEqual(s.roots(), ["C:\\A", "C:\\B"])
        # A casefolded duplicate is a no-op.
        self.assertFalse(s.add_root(TableIndex("c:\\b", {})))
        self.assertEqual(s.roots(), ["C:\\A", "C:\\B"])

    def test_remove_root_and_move_front(self):
        s = RootIndexSet([TableIndex("C:\\A", {}),
                          TableIndex("C:\\B", {}),
                          TableIndex("C:\\C", {})])
        self.assertTrue(s.move_front("c:\\c"))
        self.assertEqual(s.roots(), ["C:\\C", "C:\\A", "C:\\B"])
        self.assertTrue(s.remove_root("c:\\a"))
        self.assertEqual(s.roots(), ["C:\\C", "C:\\B"])
        self.assertFalse(s.remove_root("C:\\A"))
        self.assertFalse(s.move_front("C:\\D"))
        self.assertEqual(s.roots(), ["C:\\C", "C:\\B"])

    def test_get_first_root_wins_a_relative_path_collision(self):
        a = TableIndex("C:\\A", {"same.ct": _entry("same.ct", "C:\\A")})
        b = TableIndex("C:\\B", {"same.ct": _entry("same.ct", "C:\\B")})
        s = RootIndexSet([a, b])
        # The merged surface resolves the collision in root order.
        self.assertIs(s.get("same.ct"), a.entries["same.ct"])
        self.assertIsNone(s.get("missing.ct"))
        # The collision never hides the other entry: both are listed.
        self.assertEqual(len(s.tables()), 2)

    def test_get_by_key_matches_the_absolute_key_and_falls_back_to_relative(self):
        a = TableIndex("C:\\A", {"a.ct": _entry("a.ct", "C:\\A")})
        b = TableIndex("C:\\B", {"a.ct": _entry("a.ct", "C:\\B")})
        s = RootIndexSet([a, b])
        # The absolute key disambiguates across roots (casefolded).
        self.assertIs(s.get_by_key("c:\\b\\a.ct"), b.entries["a.ct"])
        self.assertIs(s.get_by_key("c:\\a\\a.ct"), a.entries["a.ct"])
        # A relative-path lookup is the documented fallback (first root
        # in order).
        self.assertIs(s.get_by_key("a.ct"), a.entries["a.ct"])
        self.assertIsNone(s.get_by_key("C:\\A\\missing.ct"))
        self.assertIsNone(s.get_by_key(""))

    def test_merged_entries_first_root_wins_and_is_read_only(self):
        a = TableIndex("C:\\A", {"same.ct": _entry("same.ct", "C:\\A"),
                                 "only-a.ct": _entry("only-a.ct", "C:\\A")})
        b = TableIndex("C:\\B", {"same.ct": _entry("same.ct", "C:\\B"),
                                 "only-b.ct": _entry("only-b.ct", "C:\\B")})
        s = RootIndexSet([a, b])
        self.assertEqual(sorted(s.entries),
                         ["only-a.ct", "only-b.ct", "same.ct"])
        self.assertIs(s.entries["same.ct"], a.entries["same.ct"])
        # The merged view is a computed surface - not assignable.
        with self.assertRaises(AttributeError):
            s.entries = {}

    def test_table_key_uses_the_root_when_present(self):
        self.assertEqual(table_key(_entry("sub/a.ct", "C:\\A")),
                         str(Path("C:\\A") / "sub/a.ct"))
        # A root-less entry (legacy fixture) falls back to the relative
        # path.
        self.assertEqual(table_key(_entry("sub/a.ct", "")), "sub/a.ct")


@unittest.skipIf(tk is None, "tkinter not available")
class _Mt26Base(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.tables = root / "tables"
        self.tables.mkdir()
        self.other = root / "other"
        self.other.mkdir()
        self.third = root / "third"
        self.third.mkdir()
        self.state_home = root / "state"
        self.state_home.mkdir()
        (self.tables / "a.ct").write_text(CT_GAMEA, encoding="utf-8")
        (self.other / "b.ct").write_text(CT_GAMEB, encoding="utf-8")
        self.root = tk.Tk()
        self.addCleanup(force_root_release, [self.root],
                        ((self, "root"), (self, "window"), (self, "app")))

    def _app(self, two_roots=True):
        folders = [str(self.other)] if two_roots else None
        return MasterApp(self.tables, state_home=str(self.state_home),
                         poll_ms=50, lister=_FakeLister(),
                         plan_compiler=lambda entry, name: {},
                         folders=folders)

    def _window(self, app, compiler=None):
        """One waiting-view window; a pre-seeded analysis worker is
        respected (the window resumes + queues, never double-starts)."""
        if app.analysis_worker is None:
            app.analysis_worker = AnalysisWorker(app, compiler=compiler)
        self.addCleanup(self._stop_worker, app)
        app.analysis_worker.start()
        self.window = MasterWindow(self.root, app)
        self.app = app
        return self.window

    @staticmethod
    def _stop_worker(app):
        worker = getattr(app, "analysis_worker", None)
        if worker is not None:
            worker.stop()

    def _multi_compiler(self):
        # MT-26 (0.34): the worker is addressed by the absolute table
        # key, so the fake compiler reads the file at the key path.
        def compiler(key, name):
            return _plan(hashlib.sha256(Path(key).read_bytes()).hexdigest())
        return compiler

    def _expire_interval(self, window):
        window._last_auto_rescan = (time.monotonic()
                                    - AUTO_RESCAN_INTERVAL_SECONDS - 1)

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
class MultiRootAppTests(_Mt26Base):
    """MT-26 (0.34): the folder list + multi-root index of MasterApp."""

    def test_two_root_app_indexes_both_folders(self):
        app = self._app()
        self.assertEqual(app.folders,
                         [str(self.tables.resolve()),
                          str(self.other.resolve())])
        self.assertEqual(app.folder, app.folders[0])
        self.assertEqual(app.index.roots(), app.folders)
        # Every entry carries its index root (the table key's base).
        self.assertEqual(app.index.get("a.ct").root, app.folders[0])
        self.assertEqual(app.index.get("b.ct").root, app.folders[1])
        self.assertEqual(sorted(app.index.entries), ["a.ct", "b.ct"])

    def test_a_missing_stored_root_is_visible_as_a_scan_problem(self):
        missing = self.state_home / "no-such-folder"
        app = MasterApp(self.tables, state_home=str(self.state_home),
                        poll_ms=50, lister=_FakeLister(),
                        plan_compiler=lambda entry, name: {},
                        folders=[missing])
        self.assertIn("root folder is missing or not a directory",
                      app.scan_errors[str(missing.resolve())])
        # The healthy root is unaffected.
        self.assertEqual(sorted(app.index.entries), ["a.ct"])

    def test_entry_key_absolute_in_multi_root_relative_in_single(self):
        multi = self._app()
        single = self._app(two_roots=False)
        # Multi-root: the identity key is the absolute table key.
        self.assertEqual(multi.entry_key(multi.index.get("a.ct")),
                         str(Path(multi.folders[0]) / "a.ct"))
        self.assertEqual(multi.entry_key(multi.index.get("b.ct")),
                         str(Path(multi.folders[1]) / "b.ct"))
        # Single-root: the documented relative-path identity.
        self.assertEqual(single.entry_key(single.index.get("a.ct")),
                         "a.ct")

    def test_add_folder_appends_and_refuses(self):
        app = self._app(two_roots=False)
        self.assertTrue(app.add_folder(self.third))
        self.assertEqual(app.folders, [str(self.tables.resolve()),
                                       str(self.third.resolve())])
        # Already indexed (casefolded) is a no-op.
        self.assertFalse(app.add_folder(self.third))
        # A missing / non-directory folder is a named refusal.
        with self.assertRaises(ValueError) as ctx:
            app.add_folder(self.state_home / "missing")
        self.assertIn("missing or not a directory", str(ctx.exception))
        self.assertEqual(len(app.folders), 2)

    def test_remove_folder_and_move_folder_front(self):
        app = self._app()
        # Removing a folder that is not indexed is a named refusal.
        with self.assertRaises(ValueError) as ctx:
            app.remove_folder(self.third)
        self.assertIn("not indexed", str(ctx.exception))
        app.remove_folder(self.other)
        self.assertEqual(app.folders, [str(self.tables.resolve())])
        app.add_folder(self.other)
        app.move_folder_front(self.other)
        self.assertEqual(app.folders, [str(self.other.resolve()),
                                       str(self.tables.resolve())])
        self.assertEqual(app.folder, str(self.other.resolve()))
        with self.assertRaises(ValueError):
            app.move_folder_front(self.third)

    def test_a_removed_root_disappears_from_the_index_after_rescan(self):
        app = self._app()
        self.assertEqual(len(app.index.roots()), 2)
        app.remove_folder(self.other)
        app.rescan()
        self.assertEqual(app.index.roots(), [app.folders[0]])
        self.assertIsNone(app.index.get("b.ct"))
        self.assertIsNotNone(app.index.get("a.ct"))

    def test_set_folder_replaces_the_whole_list(self):
        app = self._app()
        app.set_folder(self.other)
        self.assertEqual(app.folders, [str(self.other.resolve())])
        self.assertEqual(app.index.roots(), app.folders)
        self.assertEqual(sorted(app.index.entries), ["b.ct"])
        stored = load_master_state(app.state_path())
        self.assertEqual(stored.table_folders, tuple(app.folders))
        self.assertEqual(stored.last_folder, app.folder)

    def test_persist_state_carries_the_folder_list(self):
        app = self._app()
        app.persist_state()
        stored = load_master_state(app.state_path())
        self.assertEqual(stored.schema, MASTER_STATE_SCHEMA)
        self.assertEqual(stored.table_folders, tuple(app.folders))
        self.assertEqual(stored.last_folder, app.folder)

    def test_save_index_round_trip_carries_the_roots(self):
        app = self._app()
        app.save_index()
        raw = json.loads(app.index_path().read_bytes())
        self.assertEqual(raw["payload"]["schema"], INDEX_SET_SCHEMA)
        stored = load_index_set(app.index_path())
        self.assertEqual(stored.roots(), app.folders)
        self.assertEqual(stored.get("a.ct").root, app.folders[0])
        self.assertEqual(stored.get("b.ct").root, app.folders[1])

    def test_a_restarted_app_restores_the_stored_set(self):
        app1 = self._app()
        app1.save_index()
        app2 = self._app()
        self.assertEqual(app2.index.roots(), app1.folders)
        self.assertEqual(app2.index.get("a.ct").sha256,
                         app1.index.get("a.ct").sha256)
        self.assertEqual(app2.index.get("b.ct").sha256,
                         app1.index.get("b.ct").sha256)

    def test_a_reconcile_is_independent_per_root(self):
        app = self._app()
        old_b = app.index.get("b.ct").sha256
        # Drift the primary root's table; the other root is untouched.
        (self.tables / "a.ct").write_text(
            CT_GAMEA.replace("GameA", "GameZ"), encoding="utf-8")
        app.rescan()
        kinds = {c.relative_path: c.kind for c in app.last_changes}
        self.assertEqual(kinds["a.ct"], "changed")
        self.assertEqual(kinds["b.ct"], "unchanged")
        self.assertEqual(app.index.get("b.ct").sha256, old_b)


@unittest.skipIf(tk is None, "tkinter not available")
class CrossRootLoadTests(_Mt26Base):
    """MT-26 (0.34): the key-based explicit load paths across roots."""

    def test_request_load_resolves_the_key_in_both_roots(self):
        app = self._app()
        req_a = app.orchestrator.request_load(
            str(Path(app.folders[0]) / "a.ct"))
        self.assertEqual(req_a.table, app.index.get("a.ct"))
        req_b = app.orchestrator.request_load(
            str(Path(app.folders[1]) / "b.ct"))
        self.assertEqual(req_b.table, app.index.get("b.ct"))
        # The relative-path fallback still resolves (first root order).
        req_rel = app.orchestrator.request_load("a.ct")
        self.assertEqual(req_rel.table, app.index.get("a.ct"))

    def test_request_load_refuses_a_key_of_another_root(self):
        app = self._app()
        with self.assertRaises(ExplicitLoadRefusal) as ctx:
            app.orchestrator.request_load(str(Path(app.folders[1]) / "a.ct"))
        self.assertEqual(ctx.exception.code, "not-in-index")

    def test_choose_disambiguates_the_same_relative_path_across_roots(self):
        # Both roots carry a table with the same relative path - the
        # absolute key is the only unambiguous identity.
        (self.other / "a.ct").write_text(CT_GAMEA, encoding="utf-8")
        app = self._app()
        entry_a = app.index.index_for_root(app.folders[0]).get("a.ct")
        entry_b = app.index.index_for_root(app.folders[1]).get("a.ct")
        snap = (ProcessSnapshotEntry(7, "GameA.exe"),)
        app.orchestrator.state = STATE_CHOOSING
        app.orchestrator.choice = PendingChoice(
            "gamea.exe", "GameA.exe", snap, (entry_a, entry_b))
        outcome = app.orchestrator.choose(
            str(Path(app.folders[1]) / "a.ct"))
        self.assertTrue(outcome.ok)
        self.assertIs(app.orchestrator._load_in_flight[0], entry_b)
        # A fresh choice: the relative path resolves to the first root.
        app.orchestrator.state = STATE_CHOOSING
        app.orchestrator.choice = PendingChoice(
            "gamea.exe", "GameA.exe", snap, (entry_a, entry_b))
        outcome = app.orchestrator.choose("a.ct")
        self.assertTrue(outcome.ok)
        self.assertIs(app.orchestrator._load_in_flight[0], entry_a)


@unittest.skipIf(tk is None, "tkinter not available")
class FolderManagerUiTests(_Mt26Base):
    """MT-26 (0.34): the folder manager window + the Folder column."""

    def setUp(self):
        super().setUp()
        self.addCleanup(self._destroy_toplevels)

    def test_the_folder_manager_lists_the_roots_with_the_primary_marker(self):
        app = self._app()
        window = self._window(app, self._multi_compiler())
        window._open_folder_manager()
        tops = self._toplevels("Table folders")
        self.assertEqual(len(tops), 1)
        widgets = _all_widgets(tops[0])
        listbox = [w for w in widgets if isinstance(w, tk.Listbox)][0]
        items = [listbox.get(i) for i in range(listbox.size())]
        self.assertEqual(items, ["\u2605 " + app.folders[0],
                                 "   " + app.folders[1]])
        self.assertEqual(listbox.curselection(), (0,))
        labels = [str(w.cget("text"))
                  for w in widgets if isinstance(w, tk.Button)]
        self.assertEqual(labels, ["Add folder\u2026", "Set primary",
                                  "Remove", "Close"])

    def test_set_primary_wiring_moves_the_selected_root_front(self):
        app = self._app()
        window = self._window(app, self._multi_compiler())
        window._open_folder_manager()
        top = self._toplevels("Table folders")[0]
        widgets = _all_widgets(top)
        listbox = [w for w in widgets if isinstance(w, tk.Listbox)][0]
        listbox.selection_clear(0)
        listbox.selection_set(1)
        spy = MagicMock()
        app.move_folder_front = spy
        buttons = {str(w.cget("text")): w
                   for w in widgets if isinstance(w, tk.Button)}
        buttons["Set primary"].invoke()
        spy.assert_called_once_with(app.folders[1])

    def test_remove_wiring_removes_the_selected_root(self):
        app = self._app()
        window = self._window(app, self._multi_compiler())
        window._open_folder_manager()
        top = self._toplevels("Table folders")[0]
        widgets = _all_widgets(top)
        listbox = [w for w in widgets if isinstance(w, tk.Listbox)][0]
        listbox.selection_clear(0)
        listbox.selection_set(1)
        buttons = {str(w.cget("text")): w
                   for w in widgets if isinstance(w, tk.Button)}
        buttons["Remove"].invoke()
        self.assertEqual(app.folders, [str(self.tables.resolve())])
        self.assertEqual(app.index.roots(), app.folders)

    def test_add_wiring_appends_a_new_root(self):
        (self.third / "c.ct").write_text(CT_GAMEA, encoding="utf-8")
        app = self._app()
        window = self._window(app, self._multi_compiler())
        window._open_folder_manager()
        top = self._toplevels("Table folders")[0]
        widgets = _all_widgets(top)
        buttons = {str(w.cget("text")): w
                   for w in widgets if isinstance(w, tk.Button)}
        with patch.object(master_ui.filedialog, "askdirectory",
                          return_value=str(self.third)):
            buttons["Add folder\u2026"].invoke()
        self.assertEqual(app.folders[2], str(self.third.resolve()))
        # The re-scan picked up the new root's table immediately.
        self.assertIsNotNone(app.index.get("c.ct"))
        self.assertEqual(app.index.get("c.ct").root,
                         str(self.third.resolve()))

    def test_a_folder_manager_change_restarts_the_auto_rescan_clock(self):
        app = self._app()
        window = self._window(app, self._multi_compiler())
        window._last_auto_rescan = time.monotonic() - 100
        window._refresh_folder_view()
        self.assertLess(time.monotonic() - window._last_auto_rescan, 5)

    def test_the_folder_column_and_the_row_key_in_multi_root(self):
        app = self._app()
        window = self._window(app, self._multi_compiler())
        tree = window._table_tree
        rows = {list(tree.item(i, "values"))[0]: list(tree.item(i, "values"))
                for i in tree.get_children()}
        self.assertEqual(len(rows), 2)
        # The Folder column carries the entry's index root.
        self.assertEqual(rows["a.ct"][1], app.folders[0])
        self.assertEqual(rows["b.ct"][1], app.folders[1])
        # The row key is the absolute table key in a multi-root session.
        self.assertEqual(window._row_key(rows["a.ct"]),
                         str(Path(app.folders[0]) / "a.ct"))
        self.assertEqual(window._row_key(rows["b.ct"]),
                         str(Path(app.folders[1]) / "b.ct"))

    def test_the_row_key_stays_relative_in_a_single_root_session(self):
        app = self._app(two_roots=False)
        window = self._window(app, self._multi_compiler())
        tree = window._table_tree
        values = list(tree.item(tree.get_children()[0], "values"))
        self.assertEqual(window._row_key(values), "a.ct")


@unittest.skipIf(tk is None, "tkinter not available")
class TableLoadPickerMultiRootTests(_Mt26Base):
    """MT-26 (0.34): the table load picker's key-based labels."""

    def test_the_picker_labels_are_the_table_keys_in_multi_root(self):
        # Both roots carry a table with the same relative path.
        (self.other / "a.ct").write_text(CT_GAMEA, encoding="utf-8")
        app = self._app()
        window = self._window(app, self._multi_compiler())
        self.addCleanup(window._close_table_load_picker)
        window._open_table_load_picker()
        listbox = window._table_load_listbox
        items = [listbox.get(i) for i in range(listbox.size())]
        # Both a.ct copies (one per root) plus the other root's b.ct,
        # root order first, per-root path order inside.
        self.assertEqual(items, [str(Path(app.folders[0]) / "a.ct"),
                                 str(Path(app.folders[1]) / "a.ct"),
                                 str(Path(app.folders[1]) / "b.ct")])

    def test_the_picker_load_uses_the_key_of_the_selected_row(self):
        (self.other / "a.ct").write_text(CT_GAMEA, encoding="utf-8")
        app = self._app()
        window = self._window(app, self._multi_compiler())
        self.addCleanup(window._close_table_load_picker)
        window._open_table_load_picker()
        spy = MagicMock()
        window._load_selected_table = spy
        listbox = window._table_load_listbox
        listbox.selection_clear(0)
        listbox.selection_set(1)
        window._table_load_picker_load()
        spy.assert_called_once_with(str(Path(app.folders[1]) / "a.ct"))


class RunMasterMultiRootTests(unittest.TestCase):
    """MT-26 (0.34): the multi-root folder resolution of run_master."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.a = root / "a"
        self.a.mkdir()
        self.b = root / "b"
        self.b.mkdir()
        self.state_home = root / "state"
        self.state_home.mkdir()
        (self.a / "a.ct").write_text(CT_GAMEA, encoding="utf-8")

    def _stored(self, folders, last=None):
        save_master_state(MasterState(
            MASTER_STATE_SCHEMA,
            last if last is not None else (folders[0] if folders else None),
            table_folders=tuple(folders)),
            self.state_home / MASTER_STATE_FILENAME)

    def test_an_explicit_folder_appends_the_stored_folders(self):
        self._stored([str(self.a.resolve()), str(self.b.resolve())])
        explicit = self.state_home / "explicit"
        explicit.mkdir()
        with patch.object(master_ui.tk, "Tk"), \
                patch.object(master_ui, "MasterWindow") as window_cls, \
                patch.object(master_ui.filedialog, "askdirectory") as ask:
            with redirect_stdout(io.StringIO()) as out:
                rc = run_master(str(explicit),
                                state_home=str(self.state_home))
        self.assertEqual(rc, 0)
        ask.assert_not_called()
        app = window_cls.call_args[0][1]
        self.assertEqual(app.folders, [str(explicit.resolve()),
                                       str(self.a.resolve()),
                                       str(self.b.resolve())])
        self.assertIn("Using folder: " + str(explicit), out.getvalue())
        self.assertIn("Also indexing stored folder: "
                      + str(self.a.resolve()), out.getvalue())
        self.assertIn("Also indexing stored folder: "
                      + str(self.b.resolve()), out.getvalue())

    def test_an_explicit_folder_dedupes_against_the_stored_list(self):
        self._stored([str(self.a.resolve()), str(self.b.resolve())])
        with patch.object(master_ui.tk, "Tk"), \
                patch.object(master_ui, "MasterWindow") as window_cls, \
                patch.object(master_ui.filedialog, "askdirectory"):
            with redirect_stdout(io.StringIO()) as out:
                rc = run_master(str(self.a.resolve()),
                                state_home=str(self.state_home))
        self.assertEqual(rc, 0)
        app = window_cls.call_args[0][1]
        self.assertEqual(app.folders, [str(self.a.resolve()),
                                       str(self.b.resolve())])
        self.assertNotIn("Also indexing stored folder: "
                         + str(self.a.resolve()), out.getvalue())

    def test_a_no_arg_start_keeps_the_stored_folder_list(self):
        self._stored([str(self.a.resolve()), str(self.b.resolve())])
        with patch.object(master_ui.tk, "Tk"), \
                patch.object(master_ui, "MasterWindow") as window_cls, \
                patch.object(master_ui.filedialog, "askdirectory") as ask:
            with redirect_stdout(io.StringIO()) as out:
                rc = run_master(state_home=str(self.state_home))
        self.assertEqual(rc, 0)
        ask.assert_not_called()
        app = window_cls.call_args[0][1]
        self.assertEqual(app.folders, [str(self.a.resolve()),
                                       str(self.b.resolve())])
        self.assertIn("Using folder from last session: "
                      + str(self.a.resolve()), out.getvalue())
        self.assertIn("Also indexing stored folder: "
                      + str(self.b.resolve()), out.getvalue())

    def test_a_missing_stored_folder_is_kept_and_marked(self):
        gone = self.state_home / "gone"
        self._stored([str(self.a.resolve()), str(gone.resolve())])
        with patch.object(master_ui.tk, "Tk"), \
                patch.object(master_ui, "MasterWindow") as window_cls, \
                patch.object(master_ui.filedialog, "askdirectory") as ask:
            with redirect_stdout(io.StringIO()) as out:
                rc = run_master(state_home=str(self.state_home))
        self.assertEqual(rc, 0)
        ask.assert_not_called()
        app = window_cls.call_args[0][1]
        self.assertEqual(app.folders, [str(self.a.resolve()),
                                       str(gone.resolve())])
        self.assertIn("Also indexing stored folder: "
                      + str(gone.resolve())
                      + " (missing - scan problem)", out.getvalue())

    def test_all_stored_folders_missing_a_pick_is_prepended(self):
        gone1 = self.state_home / "gone1"
        gone2 = self.state_home / "gone2"
        self._stored([str(gone1.resolve()), str(gone2.resolve())])
        with patch.object(master_ui.tk, "Tk"), \
                patch.object(master_ui, "MasterWindow") as window_cls, \
                patch.object(master_ui.filedialog, "askdirectory",
                             return_value=str(self.a)) as ask:
            with redirect_stdout(io.StringIO()) as out:
                rc = run_master(state_home=str(self.state_home))
        self.assertEqual(rc, 0)
        self.assertEqual(ask.call_count, 1)
        app = window_cls.call_args[0][1]
        self.assertEqual(app.folders, [str(self.a.resolve()),
                                       str(gone1.resolve()),
                                       str(gone2.resolve())])
        self.assertIn("Using folder: " + str(self.a), out.getvalue())

    def test_all_stored_folders_missing_cancel_keeps_the_list(self):
        gone1 = self.state_home / "gone1"
        self._stored([str(gone1.resolve())])
        with patch.object(master_ui.tk, "Tk"), \
                patch.object(master_ui, "MasterWindow") as window_cls, \
                patch.object(master_ui.filedialog, "askdirectory",
                             return_value=""):
            with redirect_stdout(io.StringIO()) as out:
                rc = run_master(state_home=str(self.state_home))
        self.assertEqual(rc, 0)
        app = window_cls.call_args[0][1]
        self.assertEqual(app.folders, [str(gone1.resolve())])
        self.assertIn("Stored folders are missing; keeping them",
                      out.getvalue())


@unittest.skipIf(tk is None, "tkinter not available")
class AutoRescanMultiRootTests(_Mt26Base):
    """MT-26 (0.34): the auto-rescan covers every indexed root."""

    def test_the_auto_rescan_reconciles_every_root(self):
        window = self._window(self._app(), self._multi_compiler())
        # The new table lands in the NON-primary root.
        (self.other / "c.ct").write_text(
            CT_GAMEA.replace("GameA", "GameC"), encoding="utf-8")
        self.assertIsNone(self.app.index.get("c.ct"))
        self._expire_interval(window)
        window._poll()
        self.assertIsNotNone(self.app.index.get("c.ct"))
        self.assertEqual(self.app.index.get("c.ct").root,
                         self.app.folders[1])
        self.assertLess(time.monotonic() - window._last_auto_rescan, 5)


if __name__ == "__main__":
    unittest.main()
