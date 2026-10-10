"""Pure Touch-UI layout contract: sizes, rows, pages, no overlap, 56-px minimums."""
from __future__ import annotations

import unittest

from ct2trainer.native.ui_layout import (
    CARD_HEIGHT_SWITCH,
    CARD_HEIGHT_VALUE,
    LayoutError,
    MAX_PAGE_ROWS,
    MIN_WINDOW_WIDTH,
    card_height,
    cards_area_height,
    filter_change,
    initial_window_size,
    layout_violations,
    min_window_size,
    next_page,
    page_count,
    page_size_for_cards,
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
        self.assertEqual(window_columns(399), 2)
        self.assertEqual(window_columns(649), 2)
        self.assertEqual(window_columns(650), 4)
        self.assertEqual(window_columns(1920), 4)

    def test_min_window_size_depends_on_column_mode(self):
        self.assertEqual(min_window_size(400), (MIN_WINDOW_WIDTH, 720))
        self.assertEqual(min_window_size(649), (MIN_WINDOW_WIDTH, 720))
        self.assertEqual(min_window_size(650), (MIN_WINDOW_WIDTH, 610))
        self.assertEqual(min_window_size(1600), (MIN_WINDOW_WIDTH, 610))
        with self.assertRaises(LayoutError):
            min_window_size(399)


class CardAndPageTests(unittest.TestCase):
    def test_card_heights_per_view(self):
        self.assertEqual(card_height("Switches"), CARD_HEIGHT_SWITCH)
        self.assertEqual(card_height("On / Saved"), CARD_HEIGHT_SWITCH)
        self.assertEqual(card_height("Values"), CARD_HEIGHT_VALUE)
        self.assertEqual(card_height("All"), CARD_HEIGHT_VALUE)
        with self.assertRaises(LayoutError):
            card_height("Bogus")

    def test_page_size_is_clamped_to_twelve_rows(self):
        self.assertEqual(page_size_for_cards(9999, "Switches"), MAX_PAGE_ROWS)
        self.assertEqual(page_size_for_cards(9999, "Values"), MAX_PAGE_ROWS)

    def test_page_size_falls_back_to_one_row(self):
        self.assertEqual(page_size_for_cards(100, "Values"), 1)
        self.assertEqual(page_size_for_cards(0, "Switches"), 1)

    def test_400x800_value_layout_shows_exactly_two_records(self):
        # AGENTS contract: at 400x800 the value-operable Touch layout shows two records.
        cards = cards_area_height(800)
        self.assertEqual(cards, 540)
        self.assertEqual(page_size_for_cards(cards, "Values"), 2)
        self.assertEqual(layout_violations(400, 800, "Values"), [])

    def test_720x640_wide_layout_fits_one_card(self):
        self.assertEqual(layout_violations(720, 640, "Switches"), [])
        self.assertEqual(layout_violations(720, 640, "Values"), [])
        cards = cards_area_height(640)
        self.assertEqual(cards, 380)
        self.assertEqual(page_size_for_cards(cards, "Switches"), 1)
        self.assertEqual(page_size_for_cards(cards, "Values"), 1)

    def test_1920x1080_window_is_the_clamped_max_and_fits_more_switch_rows(self):
        width, height = initial_window_size(1920, 1080)
        self.assertEqual((width, height), (1600, 900))
        cards = cards_area_height(height)
        self.assertEqual(cards, 640)
        self.assertEqual(page_size_for_cards(cards, "Switches"), 3)
        self.assertEqual(page_size_for_cards(cards, "Values"), 2)


class RowContractTests(unittest.TestCase):
    def test_rows_stack_without_overlap_and_fill_the_window(self):
        rows = window_rows(800)
        names = [row.name for row in rows]
        self.assertEqual(names, ["header", "status", "toolbar", "search", "cards", "nav"])
        for left in range(len(rows)):
            for right in range(left + 1, len(rows)):
                a, b = rows[left], rows[right]
                self.assertFalse(a.top < b.bottom and b.top < a.bottom,
                                 (a.name, b.name))
        self.assertEqual(rows[0].top, 0)
        self.assertEqual(rows[-1].bottom, 800)

    def test_interactive_rows_meet_the_56px_touch_minimum(self):
        for row in window_rows(720):
            if row.name in {"header", "toolbar", "search", "nav"}:
                self.assertGreaterEqual(row.height, 56, row.name)
        self.assertEqual(window_rows(720)[3].name, "search")
        self.assertEqual(window_rows(720)[3].height, 56)

    def test_min_height_contract_610_wide_720_narrow(self):
        # wide: 610 is enough; below it is a violation
        self.assertEqual(layout_violations(720, 610, "Switches"), [])
        self.assertTrue(any("below minimum 610" in v for v in layout_violations(720, 609, "Switches")))
        # narrow: 720 is required
        self.assertTrue(any("below minimum 720" in v for v in layout_violations(400, 719, "Switches")))
        self.assertEqual(layout_violations(400, 720, "Switches"), [])

    def test_window_too_narrow_for_its_cards_reports_a_violation(self):
        violations = layout_violations(400, 500, "Values")
        self.assertTrue(any("below minimum 720" in v for v in violations))
        self.assertTrue(any("fewer than one" in v for v in violations))

    def test_unknown_view_is_rejected(self):
        with self.assertRaises(LayoutError):
            layout_violations(800, 800, "Bogus")
        with self.assertRaises(LayoutError):
            page_size_for_cards(540, "Bogus")

    def test_negative_dimensions_raise(self):
        with self.assertRaises(LayoutError):
            window_rows(-1)
        with self.assertRaises(LayoutError):
            page_size_for_cards(-5, "Switches")


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

    def test_page_count_counts_full_and_partial_pages(self):
        self.assertEqual(page_count(25, "Values", 800), 13)  # 2 per page
        self.assertEqual(page_count(4, "Values", 800), 2)
        self.assertEqual(page_count(0, "Switches", 800), 1)

    def test_filter_change_resets_page_and_preserves_drafts(self):
        drafts = {2: "12.5", 3: "ff"}
        page, kept = filter_change(5, drafts)
        self.assertEqual(page, 0)
        self.assertIs(kept, drafts)
        self.assertEqual(kept, {2: "12.5", 3: "ff"})


if __name__ == "__main__":
    unittest.main()
