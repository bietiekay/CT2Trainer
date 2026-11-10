"""Master Trainer 0.39: per-table auto-load policy wiring (MT-29).

Covers the MT-29 wiring on top of the pure ``table_autoload`` layer
(covered in ``tests/test_native_master_autoload.py``): the
orchestrator exclusion (tables whose content sha is persisted
manual-only are never auto-loaded - no request, no picker, a stable
named waiting detail instead; a mix keeps the automatic tables; the
explicit MT-10 load path is never affected; the policy set is
re-evaluated on every tick), the ``MasterApp.autoload_store`` sidecar
wiring with the ``manual_only`` predicate, the row context menu
toggle ("Auto-load: manual only" / "Auto-load: automatic", immediate
persist + status line, the disabled item for a table without a
content sha), the "Auto-load policy" row of the MT-22 details window,
and the waiting-view filter matching the persisted policy text.

``TrainerEngine`` / ``TrainerWindow`` / ``messagebox`` are patched
for the full-flow tests (the same pattern as the MT-27/28 suites);
no real process is attached.
"""
from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

try:
    import tkinter as tk
except ImportError:  # pragma: no cover - environment without Tcl/Tk
    tk = None

from test_native_master_ui import (CT_GAMEA, _FakeLister, _all_widgets)
from native_tk_teardown import force_root_release

from ct2trainer.native.master_trainer.master_ui import (MasterApp,
                                                         MasterWindow)
from ct2trainer.native.master_trainer.orchestrator import (STATE_WAITING,
                                                           MasterOrchestrator)
from ct2trainer.native.master_trainer.process_watch import (ProcessLister,
                                                            ProcessSnapshotEntry)
from ct2trainer.native.master_trainer.table_autoload import (
    AUTOLOAD_MANUAL_ONLY,
    AutoLoadStore,
)
from ct2trainer.native.master_trainer.table_index import (TableEntry,
                                                          TableIndex)


def _cand(pid, name="GameA.exe"):
    return ProcessSnapshotEntry(pid, name)


def _entry(relative_path, sha, names=("GameA.exe",)):
    return TableEntry(relative_path, 10, 20, sha, tuple(names), "ok", None)


def _index(*entries):
    return TableIndex("C:\\tables",
                      {e.relative_path: e for e in entries})


class _Lister(ProcessLister):
    def __init__(self, entries=()):
        self.entries = list(entries)

    def list_processes(self):
        return list(self.entries)


def _orch(index, snapshot, manual_only):
    compiler_calls = []

    def compiler(table, process_name):
        compiler_calls.append(table.relative_path)
        return {"plan": table.relative_path}

    orch = MasterOrchestrator(index, _Lister(snapshot), compiler,
                              now=lambda: 0.0, manual_only=manual_only)
    return orch, compiler_calls


class ManualOnlyTickTests(unittest.TestCase):
    """The orchestrator exclusion (MT-29): never auto-loads."""

    def test_all_manual_only_is_a_stable_named_suppression(self):
        sha = "ab" * 32
        index = _index(_entry("a.ct", sha))
        orch, _ = _orch(index, (_cand(1),),
                        lambda: {sha})
        outcome = orch.tick()
        self.assertIsNone(outcome.request)
        self.assertIsNone(outcome.choice)
        self.assertIn("manual-only", outcome.reason)
        self.assertIn("load one explicitly", outcome.reason)
        self.assertIsNone(orch.last_error)
        # Re-ticking is stable: the same detail, no re-issued request.
        again = orch.tick()
        self.assertIsNone(again.request)
        self.assertEqual(again.reason, outcome.reason)
        self.assertEqual(orch.state, STATE_WAITING)

    def test_a_mix_keeps_the_automatic_tables_in_the_request(self):
        manual = "aa" * 32
        auto = "bb" * 32
        index = _index(_entry("m.ct", manual), _entry("a.ct", auto))
        orch, calls = _orch(index, (_cand(1),),
                            lambda: {manual})
        outcome = orch.tick()
        self.assertIsNotNone(outcome.request)
        self.assertEqual(outcome.request.relative_path, "a.ct")
        self.assertIsNone(outcome.choice)
        orch.load(outcome.request, outcome.request_process)
        self.assertEqual(calls, ["a.ct"])

    def test_the_choice_picker_excludes_manual_only_tables(self):
        manual1 = "aa" * 32
        manual2 = "ab" * 32
        auto1 = "ac" * 32
        auto2 = "ad" * 32
        index = _index(_entry("m1.ct", manual1),
                       _entry("m2.ct", manual2),
                       _entry("a1.ct", auto1),
                       _entry("a2.ct", auto2))
        orch, _ = _orch(index, (_cand(1),),
                        lambda: {manual1, manual2})
        outcome = orch.tick()
        self.assertIsNone(outcome.request)
        self.assertIsNotNone(outcome.choice)
        self.assertEqual(sorted(t.relative_path
                                for t in outcome.choice.tables),
                         ["a1.ct", "a2.ct"])

    def test_an_explicit_load_is_never_suppressed_by_the_policy(self):
        sha = "ab" * 32
        index = _index(_entry("a.ct", sha))
        orch, _ = _orch(index, (_cand(1),), lambda: {sha})
        request = orch.request_load("a.ct")
        self.assertEqual(request.table.relative_path, "a.ct")

    def test_a_table_without_a_content_sha_is_not_excluded(self):
        other = "cd" * 32
        index = _index(_entry("plain.ct", ""))
        orch, _ = _orch(index, (_cand(1),), lambda: {other})
        outcome = orch.tick()
        # The no-sha table stays in the decision set (the ordinary
        # gate / loop-guard handling applies, unchanged).
        self.assertIsNotNone(outcome.request)
        self.assertEqual(outcome.request.relative_path, "plain.ct")

    def test_the_policy_set_is_re_evaluated_on_every_tick(self):
        sha = "ab" * 32
        index = _index(_entry("a.ct", sha))
        state = {"manual": True}
        orch, _ = _orch(index, (_cand(1),),
                        lambda: {sha} if state["manual"] else set())
        self.assertIsNone(orch.tick().request)
        state["manual"] = False
        outcome = orch.tick()
        self.assertIsNotNone(outcome.request)
        self.assertEqual(outcome.request.relative_path, "a.ct")


@unittest.skipIf(tk is None, "tkinter not available")
class AutoloadStoreWiringTests(unittest.TestCase):
    """MasterApp owns the per-table auto-load policy sidecar."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.folder = root / "tables"
        self.folder.mkdir()
        self.state_home = root / "state"
        self.state_home.mkdir()
        (self.folder / "a.ct").write_text(CT_GAMEA, encoding="utf-8")
        self.table_sha = hashlib.sha256(
            (self.folder / "a.ct").read_bytes()).hexdigest()

    def _app(self, running=()):
        return MasterApp(self.folder, state_home=self.state_home,
                         poll_ms=50, lister=_FakeLister(running),
                         plan_compiler=lambda e, n:
                         {"title": "T", "relative_path": e.relative_path})

    def test_app_has_autoload_store_fresh_home_empty(self):
        app = self._app()
        self.assertIsInstance(app.autoload_store, AutoLoadStore)
        self.assertEqual(app._manual_only_shas(), set())
        self.assertEqual(app.autoload_store.policy(self.table_sha),
                         "auto")

    def test_the_predicate_reflects_the_persisted_policy(self):
        app = self._app()
        self.assertEqual(app._manual_only_shas(), set())
        app.autoload_store.set_policy(self.table_sha,
                                      AUTOLOAD_MANUAL_ONLY)
        self.assertEqual(app._manual_only_shas(), {self.table_sha})
        # The orchestrator predicate is wired to the same method, so
        # a policy change applies from the next tick (the set is
        # re-evaluated, not cached).
        self.assertEqual(app.orchestrator._manual_only,
                         app._manual_only_shas)


@unittest.skipIf(tk is None, "tkinter not available")
class AutoloadMenuUiTests(unittest.TestCase):
    """The row context menu toggle (immediate persist, status line)."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.folder = root / "tables"
        self.folder.mkdir()
        self.state_home = root / "state"
        self.state_home.mkdir()
        (self.folder / "a.ct").write_text(CT_GAMEA, encoding="utf-8")
        self.table_sha = hashlib.sha256(
            (self.folder / "a.ct").read_bytes()).hexdigest()
        self.root = tk.Tk()
        self.addCleanup(force_root_release, [self.root],
                        ((self, "root"), (self, "window"), (self, "app")))

    def _app(self, running=()):
        return MasterApp(self.folder, state_home=self.state_home,
                         poll_ms=50, lister=_FakeLister(running),
                         plan_compiler=lambda e, n:
                         {"title": "T", "relative_path": e.relative_path})

    def _window(self, app):
        return MasterWindow(self.root, app)

    def _row_and_menu(self, window):
        rows = [c for c in window._table_tree.get_children()
                if window._is_table_row(c)]
        self.assertTrue(rows)
        created = []

        class Rec(tk.Menu):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.commands = []

            def add_command(self, label="", command=None, **kwargs):
                self.commands.append((label, command, kwargs))
                return super().add_command(label=label, command=command,
                                           **kwargs)

            def tk_popup(self, *args, **kwargs):
                pass  # never actually pop in the tests

        def factory(*args, **kwargs):
            menu = Rec(*args, **kwargs)
            created.append(menu)
            return menu

        return rows[0], created, factory

    def _context_menu(self, window, item):
        created = []

        class Rec(tk.Menu):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.commands = []

            def add_command(self, label="", command=None, **kwargs):
                self.commands.append((label, command, kwargs))
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
            window._table_context_menu(MagicMock(y=0, x_root=0, y_root=0))
        self.assertEqual(len(created), 1)
        return created[0]

    def test_the_default_menu_offers_manual_only(self):
        window = self._window(self._app())
        item, _, _ = self._row_and_menu(window)
        menu = self._context_menu(window, item)
        labels = [label for label, _cmd, _kw in menu.commands]
        self.assertIn("Auto-load: manual only", labels)
        self.assertNotIn("Auto-load: automatic", labels)

    def test_the_toggle_persists_manual_only_and_flips_the_label(self):
        app = self._app()
        window = self._window(app)
        item, _, _ = self._row_and_menu(window)
        menu = self._context_menu(window, item)
        command = dict((label, cmd) for label, cmd, _kw in menu.commands)
        command["Auto-load: manual only"]()
        self.assertEqual(app.autoload_store.policy(self.table_sha),
                         AUTOLOAD_MANUAL_ONLY)
        self.assertIn("Auto-load: manual only",
                      window._status_var.get())
        # The persisted policy survives a new app over the same home.
        other = self._app()
        self.assertEqual(other.autoload_store.policy(self.table_sha),
                         AUTOLOAD_MANUAL_ONLY)
        # The menu now offers the flip back to the documented default
        # (the toggle re-rendered the tree, so re-resolve the row).
        item2 = [c for c in window._table_tree.get_children()
                 if window._is_table_row(c)][0]
        menu2 = self._context_menu(window, item2)
        labels = [label for label, _cmd, _kw in menu2.commands]
        self.assertIn("Auto-load: automatic", labels)
        self.assertNotIn("Auto-load: manual only", labels)

    def test_the_flip_back_to_automatic_drops_the_entry(self):
        app = self._app()
        app.autoload_store.set_policy(self.table_sha,
                                      AUTOLOAD_MANUAL_ONLY)
        window = self._window(app)
        item, _, _ = self._row_and_menu(window)
        menu = self._context_menu(window, item)
        command = dict((label, cmd) for label, cmd, _kw in menu.commands)
        command["Auto-load: automatic"]()
        self.assertIsNone(app.autoload_store.get(self.table_sha))
        self.assertEqual(app.autoload_store.policy(self.table_sha),
                         "auto")
        self.assertIn("Auto-load: automatic",
                      window._status_var.get())

    def test_a_table_without_a_content_sha_gets_the_disabled_item(self):
        app = self._app()
        window = self._window(app)
        # An unreadable entry the scanner could not hash.
        bad = TableEntry("bad.ct", 0, 0, "", (), "unreadable",
                         "read failed: simulated", root=app.folder)
        app.index.indexes[0].entries["bad.ct"] = bad
        window._render_tables()
        rows = [c for c in window._table_tree.get_children()
                if window._is_table_row(c)
                and window._row_key(window._table_tree.item(c,
                                                            "values"))
                == "bad.ct"]
        self.assertTrue(rows)
        menu = self._context_menu(window, rows[0])
        item = [entry for entry in menu.commands
                if entry[0] == "Auto-load policy (no content sha)"]
        self.assertEqual(len(item), 1)
        self.assertEqual(item[0][2].get("state"), "disabled")
        self.assertNotIn("Auto-load: manual only",
                         [label for label, _c, _k in menu.commands])


@unittest.skipIf(tk is None, "tkinter not available")
class AutoloadDetailsAndFilterTests(unittest.TestCase):
    """The details-window policy row and the filter match surface."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.folder = root / "tables"
        self.folder.mkdir()
        self.state_home = root / "state"
        self.state_home.mkdir()
        (self.folder / "a.ct").write_text(CT_GAMEA, encoding="utf-8")
        self.table_sha = hashlib.sha256(
            (self.folder / "a.ct").read_bytes()).hexdigest()
        self.root = tk.Tk()
        self.addCleanup(force_root_release, [self.root],
                        ((self, "root"), (self, "window"), (self, "app")))

    def _app(self, running=()):
        return MasterApp(self.folder, state_home=self.state_home,
                         poll_ms=50, lister=_FakeLister(running),
                         plan_compiler=lambda e, n:
                         {"title": "T", "relative_path": e.relative_path})

    def _window(self, app):
        return MasterWindow(self.root, app)

    def _value_rows(self, win):
        """The details value column (the labels carry wraplength=520)."""
        labels = [w for w in _all_widgets(win) if isinstance(w, tk.Label)]
        return [str(w.cget("text"))
                for w in labels if w.cget("wraplength") == 520]

    def test_the_details_window_shows_the_policy_row(self):
        app = self._app()
        window = self._window(app)
        window._open_table_details("a.ct")
        win = window._details_win
        self.assertIsNotNone(win)
        self.assertIn("automatic (the documented default)",
                      self._value_rows(win))
        win.destroy()
        window._details_win = None
        app.autoload_store.set_policy(self.table_sha,
                                      AUTOLOAD_MANUAL_ONLY)
        window._open_table_details("a.ct")
        win = window._details_win
        self.assertIn("manual only (never auto-loaded; "
                      "load it explicitly)", self._value_rows(win))

    def test_the_filter_matches_the_persisted_policy_text(self):
        app = self._app()
        app.autoload_store.set_policy(self.table_sha,
                                      AUTOLOAD_MANUAL_ONLY)
        window = self._window(app)
        window._filter_query = "manual-only"
        window._render_tables()
        rows = [c for c in window._table_tree.get_children()
                if window._is_table_row(c)]
        self.assertEqual(len(rows), 1)
        window._filter_query = "zzz-no-match"
        window._render_tables()
        rows = [c for c in window._table_tree.get_children()
                if window._is_table_row(c)]
        self.assertEqual(len(rows), 0)
        # The default "auto" carries no match surface (documented).
        window._filter_query = "auto"
        window._render_tables()
        rows = [c for c in window._table_tree.get_children()
                if window._is_table_row(c)]
        self.assertEqual(len(rows), 0)


if __name__ == "__main__":
    unittest.main()
