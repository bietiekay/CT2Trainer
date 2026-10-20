"""Pure Touch-UI layout contract for the compact row grid (WP-58).

Window clamping, the compact chrome row stack (48 px header / filter row
with the five view chips, 32 px status, 28 px amber banners, 48 px
pagination; a 2x3 chip grid plus dedicated search row under 650 px width),
touch minimums, the row-area floor, the per-view page-size estimate and the
no-overlap stack invariants. The row model itself (heights, truncation,
hit areas, section counters) is covered in ``test_native_ui_rows`` and
``test_native_ui_group_sections``.
"""
from __future__ import annotations

import unittest

from ct2trainer.native.ui_layout import (
    BANNER_HEIGHT,
    CHROME_FILTER,
    CHROME_FILTER_GRID,
    CHROME_HEADER,
    CHROME_PAGINATION,
    CHROME_SEARCH,
    CHROME_STATUS,
    LayoutError,
    MAX_PAGE_ROWS,
    MIN_ROW_AREA,
    MIN_WINDOW_HEIGHT_NARROW,
    MIN_WINDOW_HEIGHT_WIDE,
    MIN_WINDOW_WIDTH,
    NARROW_THRESHOLD,
    ROW_HEIGHT_SECTION,
    ROW_HEIGHT_SWITCH,
    ROW_HEIGHT_VALUE,
    ROW_HEIGHT_VALUE_EXPANDED,
    STAGED_PENDING,
    TOUCH_MINIMUM,
    VIEWS,
    activation_set_record_ids,
    activation_set_summary,
    filter_change,
    initial_window_size,
    layout_violations,
    min_window_size,
    next_page,
    page_size_for_rows,
    rows_area_height,
    staged_card_state,
    staged_provider_labels,
    window_columns,
    window_rows,
)


class WindowSizeTests(unittest.TestCase):
    def test_large_screen_is_clamped_to_the_max_window(self):
        self.assertEqual(initial_window_size(1920, 1080), (1600, 900))

    def test_small_screen_is_clamped_to_the_min_window(self):
        self.assertEqual(initial_window_size(500, 500), (400, 620))

    def test_intermediate_screen_keeps_its_100px_margin(self):
        self.assertEqual(initial_window_size(1200, 800), (1100, 700))

    def test_nonpositive_screen_raises(self):
        for pair in ((0, 800), (1200, 0), (-10, 800)):
            with self.subTest(pair=pair):
                with self.assertRaises(LayoutError):
                    initial_window_size(*pair)

    def test_column_mode_switches_at_650(self):
        # Wide mode: five chips in one row. Narrow mode: 2x3 chip grid.
        self.assertEqual(window_columns(399), 2)
        self.assertEqual(window_columns(649), 2)
        self.assertEqual(window_columns(650), 5)
        self.assertEqual(window_columns(1920), 5)

    def test_min_window_size_depends_on_column_mode(self):
        self.assertEqual(min_window_size(400), (MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT_NARROW))
        self.assertEqual(min_window_size(649), (MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT_NARROW))
        self.assertEqual(min_window_size(650), (MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT_WIDE))
        self.assertEqual(min_window_size(1600), (MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT_WIDE))
        with self.assertRaises(LayoutError):
            min_window_size(399)


class RowAreaTests(unittest.TestCase):
    """Density acceptance: the row grid shows >= 10 switch rows at 1600x900."""

    def test_reference_window_1600x900_fits_at_least_ten_switch_rows(self):
        width, height = initial_window_size(1920, 1080)
        self.assertEqual((width, height), (1600, 900))
        area = rows_area_height(height, width)
        self.assertEqual(area, 724)  # 900 - 48 - 48 - 32 - 48
        self.assertGreaterEqual(page_size_for_rows(area, "Switches"), 10)
        self.assertEqual(page_size_for_rows(area, "Switches"), 11)
        self.assertEqual(layout_violations(width, height, "Switches"), [])

    def test_400x800_narrow_layout_shows_at_least_two_value_rows(self):
        # AGENTS contract: at 400x800 the value-operable Touch layout shows
        # at least two records; narrow chrome = 48 + 96 + 48 + 32 + 48 = 272.
        area = rows_area_height(800, 400)
        self.assertEqual(area, 528)
        self.assertGreaterEqual(page_size_for_rows(area, "Values"), 2)
        self.assertEqual(layout_violations(400, 800, "Values"), [])

    def test_row_heights_carry_the_touch_minimum(self):
        # Interactive rows keep the 56 px minimum; sections are display
        # headers with a 40 px group toggle.
        self.assertGreaterEqual(ROW_HEIGHT_SWITCH, 56)
        self.assertGreaterEqual(ROW_HEIGHT_VALUE, 56)
        self.assertGreaterEqual(ROW_HEIGHT_VALUE_EXPANDED, ROW_HEIGHT_VALUE)
        self.assertEqual(ROW_HEIGHT_SECTION, 48)

    def test_page_size_is_clamped_to_twelve_rows(self):
        self.assertEqual(page_size_for_rows(99999, "Switches"), MAX_PAGE_ROWS)
        self.assertEqual(page_size_for_rows(99999, "Values"), MAX_PAGE_ROWS)

    def test_page_size_falls_back_to_one_row(self):
        self.assertEqual(page_size_for_rows(100, "Values"), 1)
        self.assertEqual(page_size_for_rows(0, "Switches"), 1)

    def test_unknown_view_is_rejected(self):
        with self.assertRaises(LayoutError):
            page_size_for_rows(724, "Bogus")
        with self.assertRaises(LayoutError):
            layout_violations(800, 800, "Bogus")

    def test_negative_dimensions_raise(self):
        with self.assertRaises(LayoutError):
            window_rows(-1, 900)
        with self.assertRaises(LayoutError):
            page_size_for_rows(-5, "Switches")
        with self.assertRaises(LayoutError):
            rows_area_height(-5, 1600)


class RowContractTests(unittest.TestCase):
    def test_wide_rows_stack_without_overlap_and_fill_the_window(self):
        rows = window_rows(900, 1600)
        names = [row.name for row in rows]
        self.assertEqual(names, ["header", "filter", "status", "pagination", "rows"])
        for left in range(len(rows)):
            for right in range(left + 1, len(rows)):
                a, b = rows[left], rows[right]
                self.assertFalse(a.top < b.bottom and b.top < a.bottom,
                                 (a.name, b.name))
        self.assertEqual(rows[0].top, 0)
        self.assertEqual(rows[-1].bottom, 900)

    def test_narrow_rows_insert_the_chip_grid_and_search_row(self):
        rows = window_rows(800, 400)
        names = [row.name for row in rows]
        self.assertEqual(names, ["header", "chips", "search", "status",
                                 "pagination", "rows"])
        self.assertEqual(rows[1].height, CHROME_FILTER_GRID)
        self.assertEqual(rows[2].height, CHROME_SEARCH)
        for left in range(len(rows)):
            for right in range(left + 1, len(rows)):
                a, b = rows[left], rows[right]
                self.assertFalse(a.top < b.bottom and b.top < a.bottom,
                                 (a.name, b.name))
        self.assertEqual(rows[-1].bottom, 800)

    def test_chrome_rows_carry_the_contract_heights(self):
        rows = window_rows(900, 1600)
        by_name = {row.name: row.height for row in rows}
        self.assertEqual(by_name["header"], CHROME_HEADER)
        self.assertEqual(by_name["filter"], CHROME_FILTER)
        self.assertEqual(by_name["status"], CHROME_STATUS)
        self.assertEqual(by_name["pagination"], CHROME_PAGINATION)

    def test_banner_strips_stack_between_status_and_pagination(self):
        rows = window_rows(900, 1600, banner_count=2)
        names = [row.name for row in rows]
        self.assertEqual(names, ["header", "filter", "status", "banner0",
                                 "banner1", "pagination", "rows"])
        for name in ("banner0", "banner1"):
            self.assertEqual({row.name: row.height for row in rows}[name],
                             BANNER_HEIGHT)
        area = next(row for row in rows if row.name == "rows")
        self.assertEqual(area.height, 900 - 48 - 48 - 32 - 2 * 28 - 48)

    def test_interactive_chrome_meets_the_touch_minimum(self):
        rows = window_rows(800, 400)
        for row in rows:
            if row.name in {"header", "filter", "chips", "search", "pagination"}:
                self.assertGreaterEqual(row.height, TOUCH_MINIMUM, row.name)

    def test_min_height_contract_610_wide_720_narrow(self):
        # wide: 610 is enough; below it is a violation
        self.assertEqual(layout_violations(720, 610, "Switches"), [])
        self.assertTrue(any("below minimum 610" in v
                            for v in layout_violations(720, 609, "Switches")))
        # narrow: 720 is required
        self.assertTrue(any("below minimum 720" in v
                            for v in layout_violations(400, 719, "Switches")))
        self.assertEqual(layout_violations(400, 720, "Switches"), [])

    def test_window_too_small_reports_both_violations(self):
        # Narrow chrome is 272 px, so a 340 px window leaves a 68 px row
        # area: below the 720 minimum and too small for one value row.
        violations = layout_violations(400, 340, "Values")
        self.assertTrue(any("below minimum 720" in v for v in violations))
        self.assertTrue(any("fewer than one" in v for v in violations))

    def test_row_area_floor_is_enforced(self):
        # Wide chrome is 176 px, so a 231 px window leaves a 55 px row area:
        # below the 56 px floor even though the chrome itself is intact.
        violations = layout_violations(1600, 231, "Switches")
        self.assertTrue(any("below the 56px minimum" in v for v in violations))
        self.assertEqual(
            next(row for row in window_rows(231, 1600) if row.name == "rows").height,
            231 - 48 - 48 - 32 - 48)


class NavigationAndDraftTests(unittest.TestCase):
    def test_next_page_clamps_at_both_ends(self):
        self.assertEqual(next_page(0, -3, 25, 4), 0)
        self.assertEqual(next_page(6, 3, 25, 4), 6)   # max page = 24 // 4
        self.assertEqual(next_page(3, 5, 25, 4), 6)
        self.assertEqual(next_page(2, 1, 25, 4), 3)

    def test_next_page_with_zero_entries_has_page_zero(self):
        self.assertEqual(next_page(5, 1, 0, 4), 0)

    def test_page_size_below_one_raises(self):
        with self.assertRaises(LayoutError):
            next_page(0, 1, 10, 0)

    def test_filter_change_resets_page_and_preserves_drafts(self):
        drafts = {2: "12.5", 3: "ff"}
        page, kept = filter_change(5, drafts)
        self.assertEqual(page, 0)
        self.assertIs(kept, drafts)
        self.assertEqual(kept, {2: "12.5", 3: "ff"})


class StagedCardStateTests(unittest.TestCase):
    """WP-14 (C5): staged record state and master-toggle summary helpers."""

    def test_entry_without_staged_metadata_is_none(self):
        self.assertEqual(staged_card_state({"id": 1, "kind": "value"}, {2}), "none")
        self.assertEqual(staged_provider_labels({"id": 1, "kind": "value"}), [])

    def test_staged_entry_is_pending_until_every_provider_is_applied(self):
        entry = {"id": 3, "kind": "value",
                 "staged": {"provider_ids": [1, 2],
                            "provider_labels": ["Locate A", "Locate B"]}}
        self.assertEqual(staged_card_state(entry, set()), "pending")
        self.assertEqual(staged_card_state(entry, {1}), "pending")
        self.assertEqual(staged_card_state(entry, {1, 2}), "live")
        self.assertEqual(staged_card_state(entry, {1, 2, 7}), "live")

    def test_staged_provider_labels_follow_metadata_order(self):
        entry = {"id": 3, "staged": {"provider_ids": [1, 2],
                                     "provider_labels": ["Locate A", "Locate B"]}}
        self.assertEqual(staged_provider_labels(entry), ["Locate A", "Locate B"])

    def test_activation_set_record_ids_and_summary(self):
        entries = {
            0: {"id": 0, "label": "Master",
                "activation_sets": {"enable": [1, 2, 3], "disable": [2, 1],
                                     "source": "lua-static-extract"}},
            1: {"id": 1, "label": "Alpha"},
            2: {"id": 2, "label": "Beta"},
            3: {"id": 3, "label": "Gamma"},
        }
        entry = entries[0]
        self.assertEqual(activation_set_record_ids(entry), ([1, 2, 3], [2, 1]))
        self.assertEqual(activation_set_summary(entry, entries),
                         "Master toggle - apply: Alpha, Beta, Gamma; clear: Beta, Alpha")
        # Unknown ids fall back to the bare id.
        self.assertEqual(activation_set_summary(
            {"activation_sets": {"enable": [99]}}, entries),
            "Master toggle - apply: 99")

    def test_activation_set_summary_truncates_long_lists(self):
        entries = {i: {"id": i, "label": "R%d" % i} for i in range(12)}
        entry = {"id": 0, "activation_sets": {"enable": list(range(1, 13)),
                                               "disable": []}}
        summary = activation_set_summary(entry, entries)
        self.assertIn("R1, R2, R3", summary)
        self.assertIn("(+4 more)", summary)
        self.assertNotIn("R12", summary)

    def test_activation_set_summary_empty_for_plain_entries(self):
        self.assertEqual(activation_set_summary({"id": 1, "label": "x"}, {1: {"id": 1}}), "")
        self.assertEqual(activation_set_record_ids({"id": 1}), ([], []))


if __name__ == "__main__":
    unittest.main()
