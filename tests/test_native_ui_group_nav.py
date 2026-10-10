"""Hierarchical group navigation contract for the native Touch UI.

Pure, Tk-free coverage of the level-stack contract that turns CE groups into
"switch-into" levels: root/level entry selection, the navigable-group gate
(selected heading with plan children), enter/exit refusals, breadcrumb labels,
the view + search + level entry filter (search stays a table-wide escape
hatch; an empty search is level-scoped) and the in-group row model (the 56 px
interactive breadcrumb row between search and cards, root model unchanged).
"""
from __future__ import annotations

import unittest

from ct2trainer.native.ui_layout import (
    BREADCRUMB_ROW_HEIGHT,
    MIN_TOUCH_CONTROL,
    LayoutError,
    GroupNavigationError,
    breadcrumb_labels,
    cards_area_height,
    enter_group,
    exit_group,
    filtered_entries,
    is_navigable_group,
    layout_violations,
    level_entries,
    page_size_for_cards,
    root_entries,
    window_rows,
)


def _entries() -> dict:
    """Nested plan fixture: root -> Group A -> Subgroup B, plus edge cases.

    Plan (dict) order is the source of truth for every ordering assertion.
    """
    return {
        1: {"id": 1, "label": "Group A", "path": "Group A", "parent_id": None,
            "kind": "heading", "source_kind": "group", "selected": True,
            "supported": True,
            "reason": "Navigation heading; CE group activation is not executed."},
        2: {"id": 2, "label": "Switch Alpha", "path": "Group A / Switch Alpha",
            "parent_id": 1, "kind": "script", "source_kind": "script",
            "selected": True, "supported": True, "reason": ""},
        3: {"id": 3, "label": "Value Beta", "path": "Group A / Value Beta",
            "parent_id": 1, "kind": "value", "source_kind": "value",
            "selected": True, "supported": True, "reason": ""},
        4: {"id": 4, "label": "Subgroup B", "path": "Group A / Subgroup B",
            "parent_id": 1, "kind": "heading", "source_kind": "group",
            "selected": True, "supported": True,
            "reason": "Navigation heading; CE group activation is not executed."},
        5: {"id": 5, "label": "Switch Gamma",
            "path": "Group A / Subgroup B / Switch Gamma", "parent_id": 4,
            "kind": "script", "source_kind": "script", "selected": True,
            "supported": True, "reason": ""},
        6: {"id": 6, "label": "Root Switch", "path": "Root Switch",
            "parent_id": None, "kind": "script", "source_kind": "script",
            "selected": True, "supported": True, "reason": ""},
        7: {"id": 7, "label": "Placeholder Heading",
            "path": "Placeholder Heading", "parent_id": None,
            "kind": "heading", "source_kind": "value", "selected": True,
            "supported": True,
            "reason": "Unsupported value record rendered as a static heading."},
        8: {"id": 8, "label": "Excluded Group", "path": "Excluded Group",
            "parent_id": None, "kind": "heading", "source_kind": "group",
            "selected": False, "supported": True,
            "reason": "Not included in this trainer"},
        9: {"id": 9, "label": "Child Of Excluded",
            "path": "Excluded Group / Child Of Excluded", "parent_id": 8,
            "kind": "script", "source_kind": "script", "selected": True,
            "supported": True, "reason": ""},
        10: {"id": 10, "label": "Script With Children",
             "path": "Script With Children", "parent_id": None,
             "kind": "script", "source_kind": "script", "selected": True,
             "supported": True, "reason": ""},
        11: {"id": 11, "label": "Orphan Child",
             "path": "Script With Children / Orphan Child", "parent_id": 10,
             "kind": "script", "source_kind": "script", "selected": True,
             "supported": True, "reason": ""},
        12: {"id": 12, "label": "Unselected Root Switch",
             "path": "Unselected Root Switch", "parent_id": None,
             "kind": "script", "source_kind": "script", "selected": False,
             "supported": True, "reason": "Not included in this trainer"},
        13: {"id": 13, "label": "Unsupported Root Switch",
             "path": "Unsupported Root Switch", "parent_id": None,
             "kind": "script", "source_kind": "script", "selected": True,
             "supported": False,
             "reason": "Auto-assembler section is outside the bounded native profile."},
    }


def _ids(result) -> list:
    return [entry["id"] for entry in result]


class LevelTests(unittest.TestCase):
    def setUp(self):
        self.entries = _entries()

    def test_root_entries_in_plan_order(self):
        self.assertEqual(_ids(root_entries(self.entries)), [1, 6, 7, 8, 10, 12, 13])

    def test_root_level_equals_root_entries(self):
        self.assertEqual(level_entries(self.entries, []), root_entries(self.entries))

    def test_first_level_children(self):
        self.assertEqual(_ids(level_entries(self.entries, [1])), [2, 3, 4])

    def test_second_level_children(self):
        self.assertEqual(_ids(level_entries(self.entries, [1, 4])), [5])

    def test_unknown_level_has_no_children(self):
        self.assertEqual(level_entries(self.entries, [999]), [])

    def test_level_uses_only_the_top_of_the_stack(self):
        # Only the last stack element selects the level; earlier ids are the
        # breadcrumb trail, not part of the level query.
        self.assertEqual(level_entries(self.entries, [1, 4, 999]), [])
        self.assertEqual(_ids(level_entries(self.entries, [999, 4])), [5])


class NavigableGroupTests(unittest.TestCase):
    def setUp(self):
        self.entries = _entries()

    def test_real_groups_with_children_are_navigable(self):
        self.assertTrue(is_navigable_group(self.entries[1], self.entries))
        self.assertTrue(is_navigable_group(self.entries[4], self.entries))

    def test_placeholder_heading_without_children_is_not_navigable(self):
        # A heading derived from an unsupported value record has no plan
        # children and must stay an ordinary info card.
        self.assertFalse(is_navigable_group(self.entries[7], self.entries))

    def test_unselected_group_is_not_navigable(self):
        self.assertFalse(is_navigable_group(self.entries[8], self.entries))

    def test_script_with_children_is_not_navigable(self):
        # A script entry with children is not a group; its children stay
        # reachable through the table-wide search and the path haystack.
        self.assertFalse(is_navigable_group(self.entries[10], self.entries))

    def test_plain_script_is_not_navigable(self):
        self.assertFalse(is_navigable_group(self.entries[2], self.entries))


class EnterExitTests(unittest.TestCase):
    def setUp(self):
        self.entries = _entries()

    def test_enter_from_root(self):
        self.assertEqual(enter_group([], self.entries[1], self.entries), [1])

    def test_enter_nested_level(self):
        self.assertEqual(enter_group([1], self.entries[4], self.entries), [1, 4])

    def test_enter_returns_a_new_list(self):
        stack = []
        enter_group(stack, self.entries[1], self.entries)
        self.assertEqual(stack, [])

    def test_enter_plain_script_refuses(self):
        with self.assertRaises(GroupNavigationError):
            enter_group([], self.entries[2], self.entries)

    def test_enter_placeholder_heading_refuses(self):
        with self.assertRaises(GroupNavigationError):
            enter_group([], self.entries[7], self.entries)

    def test_enter_unselected_group_refuses(self):
        with self.assertRaises(GroupNavigationError):
            enter_group([], self.entries[8], self.entries)

    def test_exit_one_level(self):
        self.assertEqual(exit_group([1, 4]), [1])

    def test_exit_back_to_root(self):
        self.assertEqual(exit_group([1]), [])

    def test_exit_returns_a_new_list(self):
        stack = [1]
        exit_group(stack)
        self.assertEqual(stack, [1])

    def test_exit_at_root_refuses(self):
        with self.assertRaises(GroupNavigationError):
            exit_group([])

    def test_refusals_carry_visible_reasons(self):
        with self.assertRaises(GroupNavigationError) as refused:
            enter_group([], self.entries[2], self.entries)
        self.assertIn("Not a navigable group", str(refused.exception))
        self.assertIn("Switch Alpha", str(refused.exception))
        with self.assertRaises(GroupNavigationError) as refused:
            exit_group([])
        self.assertIn("Already at the root level", str(refused.exception))

    def test_group_navigation_error_is_a_value_error(self):
        self.assertTrue(issubclass(GroupNavigationError, ValueError))


class BreadcrumbTests(unittest.TestCase):
    def setUp(self):
        self.entries = _entries()

    def test_root_stack_labels(self):
        self.assertEqual(breadcrumb_labels(self.entries, []), ["Root"])

    def test_two_level_stack_labels(self):
        self.assertEqual(breadcrumb_labels(self.entries, [1, 4]),
                         ["Root", "Group A", "Subgroup B"])

    def test_unknown_id_is_refused(self):
        with self.assertRaises(GroupNavigationError):
            breadcrumb_labels(self.entries, [999])

    def test_non_group_id_is_refused(self):
        with self.assertRaises(GroupNavigationError):
            breadcrumb_labels(self.entries, [2])

    def test_unselected_group_is_refused(self):
        with self.assertRaises(GroupNavigationError):
            breadcrumb_labels(self.entries, [8])


class FilteredEntriesTests(unittest.TestCase):
    """View + search + level combination over the pure entry filter."""

    def setUp(self):
        self.entries = _entries()

    def _filter(self, view, needle, applied, desired, stack):
        return filtered_entries(self.entries, view, needle, applied, desired, stack)

    def test_root_switches_view_keeps_navigable_groups_visible(self):
        # Group A (navigable heading) stays visible so the user can drill
        # down; unselected (8) and unsupported (13) entries are hidden.
        result = self._filter("Switches", "", {}, set(), [])
        self.assertEqual(_ids(result), [1, 6, 10])

    def test_group_level_applies_before_the_view_filter(self):
        self.assertEqual(_ids(self._filter("Switches", "", {}, set(), [1])), [2, 4])
        self.assertEqual(_ids(self._filter("Switches", "", {}, set(), [1, 4])), [5])

    def test_values_view_in_group(self):
        self.assertEqual(_ids(self._filter("Values", "", {}, set(), [1])), [3, 4])

    def test_all_view_in_group_includes_the_subgroup_heading(self):
        self.assertEqual(_ids(self._filter("All", "", {}, set(), [1])), [2, 3, 4])

    def test_groups_stay_visible_in_every_view(self):
        # The navigable group stays visible in every view so the user can
        # drill down from any filter level.
        for view in ("Switches", "On / Saved", "Values", "All"):
            result = self._filter(view, "", {}, set(), [])
            self.assertIn(1, _ids(result), view)
        # Unselected groups and placeholder headings are hidden in the
        # non-All views; the All view lists every record, both included.
        for view in ("Switches", "On / Saved", "Values"):
            result = self._filter(view, "", {}, set(), [])
            self.assertNotIn(8, _ids(result), view)
            self.assertNotIn(7, _ids(result), view)
        all_view = _ids(self._filter("All", "", {}, set(), []))
        self.assertIn(7, all_view)
        self.assertIn(8, all_view)

    def test_on_saved_view_is_level_scoped(self):
        applied = {2: []}  # engine shape: dict of applied patches
        desired = {5}
        self.assertEqual(_ids(self._filter("On / Saved", "", applied, desired, [])), [1])
        self.assertEqual(_ids(self._filter("On / Saved", "", applied, desired, [1])), [2, 4])
        self.assertEqual(_ids(self._filter("On / Saved", "", applied, desired, [1, 4])), [5])

    def test_search_is_a_table_wide_escape_hatch_from_any_level(self):
        # From inside Group A, a child of Subgroup B is still findable.
        self.assertEqual(_ids(self._filter("Switches", "gamma", {}, set(), [1])), [5])

    def test_search_matches_the_ancestor_path(self):
        # "Group A" appears only in the ancestor path of entries 2 and 5.
        self.assertEqual(_ids(self._filter("Switches", "group a", {}, set(), [])), [2, 5])
        # A needle that matches the full ancestor chain selects only the leaf.
        self.assertEqual(_ids(self._filter("Switches", "group a / subgroup b", {}, set(), [])), [5])

    def test_search_still_applies_the_view_filter(self):
        self.assertEqual(self._filter("Values", "alpha", {}, set(), []), [])

    def test_search_is_case_insensitive(self):
        self.assertEqual(_ids(self._filter("Switches", "ALPHA", {}, set(), [])), [2])

    def test_empty_needle_keeps_level_scoping(self):
        # An empty needle applies the group level first: only direct
        # children of that level are candidates.
        self.assertEqual(_ids(self._filter("All", "", {}, set(), [1])),
                         _ids(level_entries(self.entries, [1])))
        self.assertEqual(_ids(self._filter("All", "", {}, set(), [1, 4])),
                         _ids(level_entries(self.entries, [1, 4])))

    def test_unselected_entries_hidden_outside_all_view(self):
        # The navigable group (1) pierces the view filter; unselected (8,
        # 12) and unsupported (13) stay hidden outside the All view.
        self.assertEqual(_ids(self._filter("Switches", "", {}, set(), [])), [1, 6, 10])
        self.assertEqual(_ids(self._filter("All", "", {}, set(), [])),
                         [1, 6, 7, 8, 10, 12, 13])

    def test_unsupported_entries_hidden_in_switches_view(self):
        self.assertNotIn(13, _ids(self._filter("Switches", "", {}, set(), [])))
        self.assertIn(13, _ids(self._filter("All", "", {}, set(), [])))

    def test_script_children_remain_reachable_via_search(self):
        # Entry 10 is not a navigable group, but its child stays reachable
        # from the root level through the table-wide search.
        self.assertEqual(_ids(self._filter("Switches", "orphan", {}, set(), [])), [11])

    def test_unknown_view_raises(self):
        with self.assertRaises(LayoutError):
            self._filter("Bogus", "", {}, set(), [])


class GroupLayoutTests(unittest.TestCase):
    def test_breadcrumb_height_meets_the_touch_minimum(self):
        self.assertEqual(BREADCRUMB_ROW_HEIGHT, MIN_TOUCH_CONTROL)

    def test_in_group_row_model_inserts_the_breadcrumb(self):
        rows = window_rows(800, in_group=True)
        self.assertEqual([row.name for row in rows],
                         ["header", "status", "toolbar", "search",
                          "breadcrumb", "cards", "nav"])
        self.assertEqual(rows[4].top, 204)
        self.assertEqual(rows[4].height, 56)
        self.assertEqual(rows[4].bottom, 260)
        self.assertEqual(rows[-1].bottom, 800)

    def test_in_group_rows_stack_without_overlap(self):
        rows = window_rows(720, in_group=True)
        for left in range(len(rows)):
            for right in range(left + 1, len(rows)):
                a, b = rows[left], rows[right]
                self.assertFalse(a.top < b.bottom and b.top < a.bottom,
                                 (a.name, b.name))

    def test_in_group_cards_shrink_by_exactly_the_breadcrumb(self):
        root = cards_area_height(800)
        in_group = cards_area_height(800, in_group=True)
        self.assertEqual(root - in_group, BREADCRUMB_ROW_HEIGHT)
        self.assertEqual(in_group, 484)

    def test_root_row_model_is_unchanged(self):
        rows = window_rows(800)
        self.assertEqual([row.name for row in rows],
                         ["header", "status", "toolbar", "search", "cards", "nav"])
        self.assertEqual(cards_area_height(800), 540)

    def test_default_equals_explicit_root(self):
        self.assertEqual(window_rows(800), window_rows(800, in_group=False))
        self.assertEqual(cards_area_height(800), cards_area_height(800, in_group=False))

    def test_in_group_page_size_uses_the_shrunk_area(self):
        # 540 px fit two value rows; 484 px fit one.
        self.assertEqual(page_size_for_cards(cards_area_height(800), "Values"), 2)
        self.assertEqual(page_size_for_cards(cards_area_height(800, in_group=True), "Values"), 1)


class GroupLayoutViolationsTests(unittest.TestCase):
    def test_breadcrumb_meets_the_touch_minimum_at_pinned_sizes(self):
        self.assertEqual(layout_violations(400, 800, "Values", in_group=True), [])

    def test_in_group_minimum_heights_still_hold(self):
        self.assertEqual(layout_violations(720, 610, "Switches", in_group=True), [])

    def test_in_group_too_small_reports_both_violations(self):
        violations = layout_violations(720, 400, "Switches", in_group=True)
        self.assertTrue(any("below minimum 610" in v for v in violations))
        self.assertTrue(any("fewer than one" in v for v in violations))

    def test_root_mode_violations_are_unchanged(self):
        self.assertEqual(layout_violations(400, 800, "Values"), [])
        violations = layout_violations(400, 500, "Values")
        self.assertTrue(any("below minimum 720" in v for v in violations))
        self.assertTrue(any("fewer than one" in v for v in violations))


if __name__ == "__main__":
    unittest.main()
