"""Staged-options UI contract (field fix 2026-10-30, South of Midnight).

Two user-facing additions:

1. moAlwaysHideChildren (CE display parity): a plan entry flagged with this
   option (plan marker ``hidden_children``) suppresses its whole subtree in
   every trainer view - the flagged parent row itself stays rendered and the
   engine-side cascade is untouched.  The row-model test uses a heading with
   a supported child so the suppression is provable (a child of a plain
   heading would otherwise render); the South-of-Midnight shape (script
   parent) is covered by the plan marker assertion in
   test_native_staged_cascade.py.
2. Staged-pending tap guard: tapping a staged-pending value row must not
   expand the inline editor; the engine's named staged refusal (raised by
   ``read_value``) is surfaced immediately in the status line.  Live or
   non-staged value rows open the editor exactly as before.

The row-model tests are headless (``ui_rows.build_rows``); the tap-guard
tests use ``TrainerWindow.__new__`` without ``__init__`` (house test style,
see test_native_ui_row_details.py).
"""
from __future__ import annotations

import tempfile
import types
import unittest
from pathlib import Path

try:
    import tkinter as tk
except ImportError:  # pragma: no cover - environment without Tcl/Tk
    tk = None

from ct2trainer.native.compiler import compile_table
from ct2trainer.native.engine import NativeRuntimeError
from ct2trainer.native.ui import TrainerWindow
from ct2trainer.native.ui_rows import (ROW_SECTION, ROW_SWITCH,
                                       STATE_STAGED, RowSnapshot, build_rows)
from test_native_staged_cascade import SOM_LIKE_CT

# A heading carrying moAlwaysHideChildren over a supported child script:
# without the marker the child renders as a switch row, with it the whole
# subtree is suppressed while the section header stays.  HIDDEN_CT_PLAIN is
# the control (no Options) used to prove the suppression is flag-driven.
HIDDEN_CT = '''<CheatTable CheatEngineTableVersion="45"><CheatEntries>
<CheatEntry><ID>10</ID><Description>"Header"</Description>
<GroupHeader>1</GroupHeader>
<Options moAlwaysHideChildren="1"/>
<CheatEntries>
<CheatEntry><ID>11</ID><Description>"Child script"</Description>
<VariableType>Auto Assembler Script</VariableType><AssemblerScript>[ENABLE]
assert(FixtureTarget.exe+60,90 90)
FixtureTarget.exe+60:
db CC 90
[DISABLE]
assert(FixtureTarget.exe+60,CC 90)
FixtureTarget.exe+60:
db 90 90
</AssemblerScript></CheatEntry>
</CheatEntries></CheatEntry>
</CheatEntries></CheatTable>'''
HIDDEN_CT_PLAIN = HIDDEN_CT.replace('<Options moAlwaysHideChildren="1"/>\n', '')


def _snapshot(applied=frozenset()):
    return RowSnapshot(applied=applied)


class HiddenChildrenRowModelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.table = self.root / "hidden.ct"
        self.table.write_text(HIDDEN_CT, encoding="utf-8")
        self.plan = compile_table(self.table, "FixtureTarget.exe")
        self.entries = {e["id"]: e for e in self.plan["entries"]}

    def test_compiler_marks_flagged_parent_with_children(self):
        self.assertIs(self.entries[10].get("hidden_children"), True)
        self.assertNotIn("hidden_children", self.entries[11])

    def test_flagged_subtree_is_suppressed_but_parent_row_stays(self):
        rows = {r.entry_id: r for r in build_rows(self.entries, "All", "", _snapshot(), 600)}
        self.assertIn(10, rows)
        self.assertEqual(rows[10].kind, ROW_SECTION)
        self.assertNotIn(11, rows)  # child subtree never rendered

    def test_control_without_flag_renders_child(self):
        # Same table without the flag: the child renders normally - proves
        # the suppression above is caused by moAlwaysHideChildren.
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        table = Path(temp.name) / "plain.ct"
        table.write_text(HIDDEN_CT_PLAIN, encoding="utf-8")
        plan = compile_table(table, "FixtureTarget.exe")
        entries = {e["id"]: e for e in plan["entries"]}
        self.assertNotIn("hidden_children", entries[10])
        rows = {r.entry_id: r for r in build_rows(entries, "All", "", _snapshot(), 600)}
        self.assertIn(10, rows)
        self.assertIn(11, rows)

    def test_hidden_child_absent_from_switches_view(self):
        rows = {r.entry_id: r for r in build_rows(self.entries, "Switches", "", _snapshot(), 600)}
        self.assertNotIn(11, rows)  # hidden child never renders

    def test_som_shape_plan_and_rows(self):
        # The South-of-Midnight-shaped two-level plan: the flagged master
        # renders, its hidden child does not, and both staged values keep
        # their pending sublabel.
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        som_table = Path(temp.name) / "som_like.ct"
        som_table.write_text(SOM_LIKE_CT, encoding="utf-8")
        plan = compile_table(som_table, "FixtureTarget.exe")
        entries = {e["id"]: e for e in plan["entries"]}
        rows = {r.entry_id: r for r in build_rows(entries, "All", "", _snapshot(), 600)}
        self.assertIn(1, rows)  # master row stays the interface
        self.assertNotIn(2, rows)
        self.assertEqual(rows[3].state, STATE_STAGED)
        self.assertIn("unlocks when active:", rows[3].sublabel)
        self.assertEqual(rows[4].state, STATE_STAGED)
        # With the master live the staged rows flip to off (usable), not hidden.
        rows_live = {r.entry_id: r for r in
                     build_rows(entries, "All", "", _snapshot(applied=frozenset({1, 2})), 600)}
        self.assertIn(1, rows_live)
        self.assertNotIn(rows_live[3].state, (STATE_STAGED,))


def _window_stub(root, entry, applied=frozenset()):
    """TrainerWindow without __init__ (house test style, see
    test_native_ui_row_details.py): enough state for the tap-guard helper."""
    window = TrainerWindow.__new__(TrainerWindow)
    window.root = root
    window.engine = types.SimpleNamespace(
        entries={entry["id"]: entry}, applied=applied, entry_errors={})
    window._status_text = tk.StringVar(value="")
    window.expanded_values = frozenset()
    window.render = lambda: None
    window._update_banners = lambda: None
    return window


def _staged_entry(provider_id=1):
    return {
        "id": 3,
        "label": "Value on A",
        "path": "Value on A",
        "kind": "value",
        "supported": True,
        "selected": True,
        "staged": {"provider_ids": [provider_id], "provider_labels": ["Master"]},
    }


@unittest.skipUnless(tk is not None, "tkinter required for real widget construction")
class StagedTapGuardTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()

    def tearDown(self):
        self.root.destroy()

    def test_pending_value_tap_refuses_editor_and_names_provider(self):
        window = _window_stub(self.root, _staged_entry())
        calls = []

        def read_value(identifier):
            calls.append(identifier)
            raise NativeRuntimeError(
                "Staged record 'Value on A' requires active provider 'Master'")

        window.engine.read_value = read_value
        window._open_value_editor(3)
        self.assertEqual(calls, [3])
        self.assertNotIn(3, window.expanded_values)
        self.assertEqual(window._status_text.get(),
                         "Staged record 'Value on A' requires active provider 'Master'")

    def test_live_value_tap_opens_editor_without_read(self):
        window = _window_stub(self.root, _staged_entry(), applied=frozenset({1}))

        def boom(_):
            raise AssertionError("read_value must not run for a live staged value")

        window.engine.read_value = boom
        window._open_value_editor(3)
        self.assertIn(3, window.expanded_values)

    def test_non_staged_value_tap_opens_editor(self):
        entry = {"id": 7, "label": "Plain", "path": "Plain", "kind": "value",
                 "supported": True, "selected": True}
        window = _window_stub(self.root, entry)

        def boom(_):
            raise AssertionError("read_value must not run for a plain value")

        window.engine.read_value = boom
        window._open_value_editor(7)
        self.assertIn(7, window.expanded_values)


if __name__ == "__main__":
    unittest.main()
