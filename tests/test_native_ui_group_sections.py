"""Group section contract for the native Touch UI row grid (WP-58).

Pure, Tk-free coverage of the section model that replaces the old
breadcrumb drill-down: 48 px section header rows (chevron + name + counter),
default-expanded nested sections indented by 12 px per level, collapse
through ``collapsed_sections`` (the header stays, the subtree hides), the
"n/N on" subtree counter with its record-count fallback, and the 32x40 group
toggle pill that appears only for headings carrying a ``parent_activation``
flag (moBindActivation headings stay plain).
"""
from __future__ import annotations

import unittest

from ct2trainer.native.ui_layout import ROW_HEIGHT_SECTION, ROW_INDENT_STEP
from ct2trainer.native.ui_rows import (
    ACCENT_OFF,
    ACCENT_ON,
    RowSnapshot,
    build_rows,
)


def _entries() -> dict:
    """Nested plan fixture: root -> Group A -> Subgroup B, plus edge groups.

    Plan (dict) order is the source of truth for every ordering assertion.
    """
    return {
        1: {"id": 1, "label": "Group A", "path": "Group A", "parent_id": None,
            "kind": "heading", "selected": True, "supported": True,
            "parent_activation": "direct_activation", "reason": ""},
        2: {"id": 2, "label": "Switch Alpha", "path": "Group A / Switch Alpha",
            "parent_id": 1, "kind": "script", "selected": True, "supported": True,
            "reason": ""},
        3: {"id": 3, "label": "Value Beta", "path": "Group A / Value Beta",
            "parent_id": 1, "kind": "value", "selected": True, "supported": True,
            "reason": "", "variable_type": "4bytes"},
        4: {"id": 4, "label": "Subgroup B", "path": "Group A / Subgroup B",
            "parent_id": 1, "kind": "heading", "selected": True, "supported": True,
            "reason": ""},
        5: {"id": 5, "label": "Switch Gamma",
            "path": "Group A / Subgroup B / Switch Gamma", "parent_id": 4,
            "kind": "script", "selected": True, "supported": True, "reason": ""},
        6: {"id": 6, "label": "Root Switch", "path": "Root Switch",
            "parent_id": None, "kind": "script", "selected": True,
            "supported": True, "reason": ""},
        7: {"id": 7, "label": "Bind Group", "path": "Bind Group",
            "parent_id": None, "kind": "heading", "selected": True,
            "supported": True, "parent_mo_bind": True, "reason": ""},
        8: {"id": 8, "label": "Bind Child", "path": "Bind Group / Bind Child",
            "parent_id": 7, "kind": "script", "selected": True, "supported": True,
            "reason": ""},
        9: {"id": 9, "label": "Placeholder", "path": "Placeholder",
            "parent_id": None, "kind": "heading", "selected": True,
            "supported": True,
            "reason": "Unsupported value record rendered as a static heading."},
        10: {"id": 10, "label": "Address Group", "path": "Address Group",
             "parent_id": None, "kind": "heading", "selected": True,
             "supported": True, "reason": "",
             "address_provider": {"label": "Base", "value_type": "qword"}},
        11: {"id": 11, "label": "Address Child",
             "path": "Address Group / Address Child", "parent_id": 10,
             "kind": "script", "selected": True, "supported": True, "reason": ""},
        12: {"id": 12, "label": "Excluded Group", "path": "Excluded Group",
             "parent_id": None, "kind": "heading", "selected": False,
             "supported": True, "reason": "Not included in this trainer"},
        13: {"id": 13, "label": "Excluded Child",
             "path": "Excluded Group / Excluded Child", "parent_id": 12,
             "kind": "script", "selected": False, "supported": True,
             "reason": "Not included in this trainer"},
        14: {"id": 14, "label": "Shell Group", "path": "Shell Group",
             "parent_id": None, "kind": "heading", "selected": True,
             "supported": True, "reason": ""},
        15: {"id": 15, "label": "Inner Shell", "path": "Shell Group / Inner Shell",
             "parent_id": 14, "kind": "heading", "selected": True,
             "supported": True, "reason": ""},
        16: {"id": 16, "label": "Value Only Group", "path": "Value Only Group",
             "parent_id": None, "kind": "heading", "selected": True,
             "supported": True, "reason": ""},
        17: {"id": 17, "label": "Value Omega", "path": "Value Only Group / Value Omega",
             "parent_id": 16, "kind": "value", "selected": True, "supported": True,
             "reason": "", "variable_type": "4bytes"},
        18: {"id": 18, "label": "Value Phi", "path": "Value Only Group / Value Phi",
             "parent_id": 16, "kind": "value", "selected": True, "supported": True,
             "reason": "", "variable_type": "float"},
    }


def _snap(**kwargs) -> RowSnapshot:
    base = dict(applied=frozenset(), desired=frozenset(), frozen=frozenset(),
                errors={}, value_applied=frozenset(), parent_active=frozenset(),
                pulsing=frozenset(), confirmed=frozenset(), disconnected=False)
    base.update(kwargs)
    return RowSnapshot(**base)


def _rows(view="Switches", width=800, **snapshot):
    return build_rows(_entries(), view, "", _snap(**snapshot), width)


def _by_id(rows, entry_id):
    return next(row for row in rows if row.entry_id == entry_id)


class SectionRowTests(unittest.TestCase):
    def setUp(self):
        self.rows = _rows()

    def test_section_headers_replace_the_drill_down_in_plan_order(self):
        # One flat page: section headers inline with their (nested) children.
        self.assertEqual([row.entry_id for row in self.rows],
                         [1, 2, 4, 5, 6, 7, 8, 10, 11])
        for row in self.rows:
            if row.kind == "section":
                self.assertEqual(row.height, ROW_HEIGHT_SECTION)

    def test_sections_default_to_expanded(self):
        self.assertTrue(_by_id(self.rows, 1).expanded)
        self.assertTrue(_by_id(self.rows, 4).expanded)
        self.assertTrue(_by_id(self.rows, 7).expanded)

    def test_children_indented_by_the_12px_step_per_level(self):
        self.assertEqual(_by_id(self.rows, 2).indent, ROW_INDENT_STEP)
        self.assertEqual(_by_id(self.rows, 5).indent, 2 * ROW_INDENT_STEP)
        self.assertEqual(_by_id(self.rows, 6).indent, 0)
        self.assertEqual(_by_id(self.rows, 8).indent, ROW_INDENT_STEP)

    def test_collapse_hides_the_subtree_but_keeps_the_header(self):
        rows = build_rows(_entries(), "Switches", "", _snap(), 800,
                          collapsed_sections=frozenset({1}))
        self.assertEqual([row.entry_id for row in rows], [1, 6, 7, 8, 10, 11])
        header = _by_id(rows, 1)
        self.assertFalse(header.expanded)
        self.assertIsNotNone(header.chevron)
        # The counter keeps counting the hidden subtree.
        self.assertEqual(header.counter, "0/2 on")

    def test_nested_collapse_only_hides_that_subtree(self):
        rows = build_rows(_entries(), "Switches", "", _snap(), 800,
                          collapsed_sections=frozenset({4}))
        self.assertEqual([row.entry_id for row in rows],
                         [1, 2, 4, 6, 7, 8, 10, 11])
        self.assertFalse(_by_id(rows, 4).expanded)
        self.assertTrue(_by_id(rows, 1).expanded)

    def test_expansion_state_does_not_leak_between_builds(self):
        rows = build_rows(_entries(), "Switches", "", _snap(), 800)
        self.assertTrue(all(row.expanded for row in rows if row.kind == "section"))


class SectionCounterTests(unittest.TestCase):
    def test_counter_counts_the_whole_subtree_including_nested_groups(self):
        rows = _rows(applied=frozenset({5}))
        self.assertEqual(_by_id(rows, 1).counter, "1/2 on")
        rows = _rows(applied=frozenset({2, 5}))
        self.assertEqual(_by_id(rows, 1).counter, "2/2 on")
        rows = _rows()
        self.assertEqual(_by_id(rows, 1).counter, "0/2 on")

    def test_counter_ignores_unselected_and_unsupported_records(self):
        entries = _entries()
        entries[5]["selected"] = False
        rows = build_rows(entries, "Switches", "", _snap(applied=frozenset({5})), 800)
        self.assertEqual(_by_id(rows, 1).counter, "0/1 on")

    def test_counter_counts_subtree_scripts_regardless_of_the_view(self):
        # Group A holds Switch Alpha and Switch Gamma plus Value Beta; the
        # switch counter ignores the current view.
        rows = build_rows(_entries(), "Values", "", _snap(), 800)
        self.assertEqual(_by_id(rows, 1).counter, "0/2 on")

    def test_counter_falls_back_to_a_record_count_for_value_only_groups(self):
        rows = build_rows(_entries(), "Values", "", _snap(), 800)
        # Value Only Group (16) holds two selected value records, no scripts.
        self.assertEqual(_by_id(rows, 16).counter, "2 records")
        entries = _entries()
        del entries[18]
        rows = build_rows(entries, "Values", "", _snap(), 800)
        self.assertEqual(_by_id(rows, 16).counter, "1 record")

    def test_counter_is_empty_when_the_subtree_holds_no_counted_records(self):
        rows = build_rows(_entries(), "All", "", _snap(), 800)
        # Shell Group (14) nests only another heading, so nothing is counted.
        self.assertEqual(_by_id(rows, 14).counter, "")
        # Excluded Group (12) counts its unselected child as a plain record.
        self.assertEqual(_by_id(rows, 12).counter, "1 record")

    def test_counter_counts_values_as_records_even_with_switches_elsewhere(self):
        # Subgroup B holds only Switch Gamma, so its counter is switch-based.
        rows = _rows()
        self.assertEqual(_by_id(rows, 4).counter, "0/1 on")


class GroupToggleTests(unittest.TestCase):
    def test_toggle_pill_only_for_parent_activation_headings(self):
        rows = _rows()
        flagged = _by_id(rows, 1)
        self.assertTrue(flagged.group_toggle)
        self.assertEqual((flagged.group_toggle_hit.x, flagged.group_toggle_hit.w,
                          flagged.group_toggle_hit.h), (800 - 8 - 32, 32, 40))
        # Plain moHideChildren subgroup: chevron + counter only.
        plain = _by_id(rows, 4)
        self.assertFalse(plain.group_toggle)
        self.assertIsNone(plain.group_toggle_hit)
        # moBindActivation carries no parent_activation: no cascade pill.
        bind = _by_id(rows, 7)
        self.assertFalse(bind.group_toggle)
        self.assertIsNone(bind.group_toggle_hit)

    def test_toggle_pill_state_follows_the_parent_active_snapshot(self):
        off = _by_id(_rows(), 1)
        self.assertEqual(off.state, "off")
        self.assertEqual(off.accent, ACCENT_OFF)
        on = _by_id(_rows(parent_active=frozenset({1})), 1)
        self.assertEqual(on.state, "on")
        self.assertEqual(on.accent, ACCENT_ON)

    def test_pill_hit_is_a_sub_rect_of_the_row(self):
        row = _by_id(_rows(), 1)
        self.assertTrue(row.group_toggle_hit.contains(800 - 20, row.y + 20))
        self.assertFalse(row.group_toggle_hit.contains(800 - 20, row.y + 45))


class SectionVisibilityTests(unittest.TestCase):
    def setUp(self):
        self.rows = _rows()

    def test_section_shows_when_itself_or_any_descendant_is_visible(self):
        # Search for the nested child: both ancestor headers stay visible.
        rows = build_rows(_entries(), "Switches", "gamma", _snap(), 800)
        self.assertEqual([row.entry_id for row in rows], [1, 4, 5])

    def test_unselected_group_hidden_outside_the_all_view(self):
        rows = _rows("Switches")
        self.assertNotIn(12, [row.entry_id for row in rows])
        all_rows = _rows("All")
        self.assertIn(12, [row.entry_id for row in all_rows])
        self.assertIn(13, [row.entry_id for row in all_rows])

    def test_placeholder_heading_renders_as_a_dim_info_row(self):
        rows = build_rows(_entries(), "All", "", _snap(), 800)
        row = _by_id(rows, 9)
        self.assertEqual(row.kind, "info")
        self.assertEqual(row.height, ROW_HEIGHT_SECTION)
        self.assertEqual(row.sublabel,
                         "Unsupported value record rendered as a static heading.")
        self.assertFalse(row.group_toggle)

    def test_address_provider_marker_shows_as_the_section_sublabel(self):
        row = _by_id(self.rows, 10)
        self.assertEqual(row.sublabel, "Address provided at runtime")
        self.assertEqual(_by_id(self.rows, 1).sublabel, "")


if __name__ == "__main__":
    unittest.main()
