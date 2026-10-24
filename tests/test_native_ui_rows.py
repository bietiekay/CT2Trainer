"""Pure row-model contract for the native Touch UI row grid (WP-58).

Tk-free coverage of ``ui_rows``: deterministic label truncation, snapshot
validation, the six view filters (Switches/On/Saved/Values/Scripts/All)
with the table-wide search, per-D6 state-to-accent mapping, row heights
and hit geometry, the transient pulse/confirm tints, the value-row "on"
rule (session value writes only), the inline editor rectangles of the
expanded value row and the mixed-content page slicing.
"""
from __future__ import annotations

import unittest
from unittest import mock

from ct2trainer.native.ui_layout import STAGED_PENDING, VIEWS
from ct2trainer.native.ui_rows import (
    ACCENT_OFF,
    ACCENT_ON,
    BADGE_FROZEN,
    RowModelError,
    RowSnapshot,
    build_rows,
    find_row,
    slice_pages,
    text_width,
    truncate_label,
)


def _entries() -> dict:
    """Flat plan fixture covering every record state the row model renders."""
    return {
        1: {"id": 1, "label": "Switch One", "path": "Switch One",
            "parent_id": None, "kind": "script", "selected": True,
            "supported": True, "reason": ""},
        2: {"id": 2, "label": "Switch Two", "path": "Switch Two",
            "parent_id": None, "kind": "script", "selected": True,
            "supported": True, "reason": "", "one_shot": True},
        3: {"id": 3, "label": "Value Three", "path": "Value Three",
            "parent_id": None, "kind": "value", "selected": True,
            "supported": True, "reason": "", "variable_type": "4bytes"},
        4: {"id": 4, "label": "Unselected", "path": "Unselected",
            "parent_id": None, "kind": "script", "selected": False,
            "supported": True, "reason": "Not selected in the converter"},
        5: {"id": 5, "label": "Unsupported", "path": "Unsupported",
            "parent_id": None, "kind": "script", "selected": True,
            "supported": False,
            "reason": "Outside the bounded native profile"},
        6: {"id": 6, "label": "Staged Value", "path": "Staged Value",
            "parent_id": None, "kind": "value", "selected": True,
            "supported": True, "reason": "", "variable_type": "4bytes",
            "staged": {"provider_ids": [1], "provider_labels": ["Locate A"]}},
        7: {"id": 7, "label": "Master Switch", "path": "Master Switch",
            "parent_id": None, "kind": "script", "selected": True,
            "supported": True, "reason": "",
            "activation_sets": {"enable": [1, 2], "disable": [],
                                 "source": "lua-static-extract"}},
    }


def _snap(**kwargs) -> RowSnapshot:
    base = dict(applied=frozenset(), desired=frozenset(), frozen=frozenset(),
                errors={}, value_applied=frozenset(), parent_active=frozenset(),
                pulsing=frozenset(), confirmed=frozenset(), disconnected=False)
    base.update(kwargs)
    return RowSnapshot(**base)


def _rows(view="Switches", width=800, **snapshot) -> list:
    return build_rows(_entries(), view, "", _snap(**snapshot), width)


def _by_id(rows, entry_id):
    return next(row for row in rows if row.entry_id == entry_id)


class TruncationTests(unittest.TestCase):
    """D9: deterministic, byte-verifiable truncation (same input -> same output)."""

    def test_text_width_uses_the_fixed_char_weight_table(self):
        # lowercase 0.52 / uppercase 0.68 / ellipsis 0.60, scaled by size
        self.assertEqual(text_width("abc", 12), 19)      # 3 * 0.52 * 12 = 18.72 -> 19
        self.assertEqual(text_width("ABC", 12), 24)      # 3 * 0.68 * 12 = 24.48 -> 24
        self.assertEqual(text_width("abc", 11), 17)      # scales with the font size
        self.assertEqual(text_width("\u2026", 12), 7)

    def test_truncate_returns_the_normalized_input_when_it_fits(self):
        self.assertEqual(truncate_label("Short label", 200), "Short label")

    def test_truncate_collapses_whitespace_runs_and_newlines(self):
        self.assertEqual(truncate_label("a\n\t  b   c", 200), "a b c")

    def test_truncate_ellipsizes_to_the_longest_fitting_prefix(self):
        label = "x" * 100
        result = truncate_label(label, 50, size=12)
        self.assertTrue(result.endswith("\u2026"))
        self.assertTrue(label.startswith(result[:-1]))
        self.assertLessEqual(text_width(result, 12), 50)

    def test_truncate_is_deterministic(self):
        label = "Stealth Mode with a very long descriptive suffix"
        first = truncate_label(label, 96)
        for _ in range(3):
            self.assertEqual(truncate_label(label, 96), first)

    def test_truncate_returns_empty_when_even_the_ellipsis_does_not_fit(self):
        self.assertEqual(text_width("\u2026", 12), 7)
        self.assertEqual(truncate_label("x" * 20, 6), "")

    def test_truncate_refuses_bad_input(self):
        with self.assertRaises(RowModelError):
            truncate_label(5, 100)
        with self.assertRaises(RowModelError):
            truncate_label("x", -1)
        with self.assertRaises(RowModelError):
            text_width(5)

    def test_text_width_of_empty_string_is_zero(self):
        self.assertEqual(text_width("", 12), 0)


class SnapshotTests(unittest.TestCase):
    def test_defaults_are_empty_and_valid(self):
        snap = RowSnapshot()
        self.assertEqual(snap.applied, frozenset())
        self.assertFalse(snap.disconnected)

    def test_plain_sets_are_rejected(self):
        with self.assertRaises(RowModelError):
            RowSnapshot(applied={1, 2})

    def test_non_integer_ids_are_rejected(self):
        with self.assertRaises(RowModelError):
            RowSnapshot(applied=frozenset({"a"}))

    def test_errors_must_map_integer_ids_to_text(self):
        with self.assertRaises(RowModelError):
            RowSnapshot(errors={1: 42})

    def test_disconnected_must_be_a_boolean(self):
        with self.assertRaises(RowModelError):
            RowSnapshot(disconnected="yes")


class FilterTests(unittest.TestCase):
    """The six D1/D7 views plus the table-wide, casefolded search."""

    def setUp(self):
        self.entries = _entries()

    def _filter(self, view, needle="", applied=frozenset(), desired=frozenset()):
        from ct2trainer.native.ui_rows import filter_entries
        return filter_entries(self.entries, view, needle, applied, desired)

    def test_views_select_their_record_class(self):
        self.assertEqual([e["id"] for e in self._filter("Switches")], [1, 2, 7])
        self.assertEqual([e["id"] for e in self._filter("Values")], [3, 6])
        self.assertEqual([e["id"] for e in self._filter("All")],
                         [1, 2, 3, 4, 5, 6, 7])

    def test_on_view_needs_the_engine_applied_set(self):
        self.assertEqual([e["id"] for e in self._filter("On", applied=frozenset({2, 7}))], [2, 7])
        self.assertEqual(self._filter("On"), [])

    def test_saved_view_needs_the_desired_set(self):
        self.assertEqual([e["id"] for e in self._filter("Saved", desired=frozenset({1}))], [1])
        self.assertEqual(self._filter("Saved"), [])

    def test_scripts_view_lists_every_script_record_only(self):
        # Every kind == "script" entry, blocked (5) and unselected (4)
        # included; value records (3, 6) excluded.
        self.assertEqual([e["id"] for e in self._filter("Scripts")], [1, 2, 4, 5, 7])

    def test_scripts_view_hides_values_and_headings(self):
        from ct2trainer.native.ui_rows import filter_entries
        entries = dict(self.entries)
        entries[8] = {"id": 8, "label": "A Heading", "path": "A Heading",
                      "parent_id": None, "kind": "heading", "selected": True,
                      "supported": True, "reason": "", "requires": [],
                      "provides": [], "dependency_ids": []}
        entries[9] = {"id": 9, "label": "Hidden Value", "path": "Hidden Value",
                      "parent_id": None, "kind": "value", "selected": True,
                      "supported": True, "reason": "", "requires": [],
                      "provides": [], "dependency_ids": [],
                      "variable_type": "4 Bytes", "show_as_hex": False,
                      "show_as_signed": None, "dropdown": {"choices": [], "read_only": False}}
        ids = [e["id"] for e in
               filter_entries(entries, "Scripts", "", frozenset(), frozenset())]
        self.assertNotIn(8, ids)
        self.assertNotIn(9, ids)
        self.assertEqual([e["id"] for e in self._filter("Scripts")], [1, 2, 4, 5, 7])

    def test_unselected_and_unsupported_appear_in_all_and_scripts(self):
        for view in ("Switches", "On", "Saved", "Values"):
            self.assertNotIn(4, [e["id"] for e in self._filter(view)], view)
            self.assertNotIn(5, [e["id"] for e in self._filter(view)], view)
        for view in ("All", "Scripts"):
            ids = [e["id"] for e in self._filter(view)]
            self.assertIn(4, ids, view)
            self.assertIn(5, ids, view)

    def test_search_is_a_table_wide_casefolded_haystack(self):
        self.assertEqual([e["id"] for e in self._filter("Switches", "SWITCH TWO")], [2])
        # the id token is part of the haystack
        self.assertEqual([e["id"] for e in self._filter("All", "2")], [2])

    def test_search_still_applies_the_view_filter(self):
        self.assertEqual(self._filter("Values", "switch"), [])

    def test_search_without_hits_is_empty(self):
        self.assertEqual(self._filter("Switches", "zzz"), [])

    def test_unknown_view_raises(self):
        with self.assertRaises(RowModelError):
            self._filter("Bogus")
        self.assertNotIn("Bogus", VIEWS)


class BuildRowsTests(unittest.TestCase):
    """Row kinds, heights, plan order and the D6 state table."""

    def test_switch_and_value_rows_carry_the_contract_heights(self):
        rows = build_rows(_entries(), "All", "", _snap(), 800)
        self.assertEqual(_by_id(rows, 1).height, 64)     # switch
        self.assertEqual(_by_id(rows, 3).height, 72)     # value collapsed
        self.assertEqual(_by_id(rows, 4).height, 48)     # info (unselected)

    def test_plan_order_is_the_row_order(self):
        rows = _rows("All")
        self.assertEqual([row.entry_id for row in rows], [1, 2, 3, 4, 5, 6, 7])

    def test_switches_view_hides_blocked_and_values(self):
        rows = _rows("Switches")
        self.assertEqual([row.entry_id for row in rows], [1, 2, 7])
        self.assertTrue(all(row.kind == "switch" for row in rows))

    def test_off_state_uses_the_neutral_accent(self):
        row = _by_id(_rows(), 1)
        self.assertEqual(row.state, "off")
        self.assertEqual(row.accent, ACCENT_OFF)

    def test_on_state_uses_the_green_accent(self):
        row = _by_id(_rows("Switches", applied=frozenset({1})), 1)
        self.assertEqual(row.state, "on")
        self.assertEqual(row.accent, ACCENT_ON)
        self.assertTrue(row.pill_on)

    def test_error_state_keeps_the_red_dot_flag(self):
        row = _by_id(_rows("Switches", errors={2: "Byte assertion failed"}), 2)
        self.assertEqual(row.state, "error")
        self.assertTrue(row.error_dot)

    def test_staged_value_row_carry_the_provider_sublabel(self):
        row = _by_id(_rows("Values"), 6)   # provider 1 not applied
        self.assertEqual(row.state, "staged")
        self.assertEqual(row.sublabel, "unlocks when active: Locate A")
        self.assertEqual(STAGED_PENDING, "pending")

    def test_staged_state_becomes_live_once_every_provider_is_applied(self):
        row = _by_id(_rows("Values", applied=frozenset({1})), 6)
        self.assertEqual(row.state, "off")
        self.assertEqual(row.sublabel, "")

    def test_blocked_record_renders_as_dim_info_row_with_exact_reason(self):
        rows = _rows("All")
        row = _by_id(rows, 4)
        self.assertEqual(row.kind, "info")
        self.assertEqual(row.sublabel, "Not selected in the converter")
        self.assertEqual(row.state, "blocked")
        self.assertEqual(row.tint, "#141a24")

    def test_unselected_record_without_reason_gets_the_default_reason(self):
        entries = _entries()
        entries[4]["reason"] = ""
        row = _by_id(build_rows(entries, "All", "", _snap(), 800), 4)
        self.assertEqual(row.sublabel, "Not included in this trainer")

    def test_pulse_tint_overrides_the_state_tint(self):
        row = _by_id(_rows("Switches", pulsing=frozenset({1})), 1)
        self.assertEqual(row.tint, "#2c3d58")
        self.assertTrue(row.pulsing)
        self.assertFalse(row.confirmed)

    def test_confirmed_flag_only_comes_from_the_snapshot(self):
        row = _by_id(_rows("Switches", confirmed=frozenset({2})), 2)
        self.assertTrue(row.confirmed)

    def test_value_row_is_on_only_via_a_session_value_write(self):
        # applied switches never switch the value-row accent on...
        row = _by_id(_rows("Values", applied=frozenset({1})), 3)
        self.assertEqual(row.state, "off")
        # ...the session value-applied set does
        row = _by_id(_rows("Values", value_applied=frozenset({3})), 3)
        self.assertEqual(row.state, "on")
        self.assertEqual(row.accent, ACCENT_ON)

    def test_frozen_value_row_shows_the_badge_not_the_accent(self):
        row = _by_id(_rows("Values", frozen=frozenset({3})), 3)
        self.assertTrue(row.frozen_badge)
        self.assertEqual(row.state, "off")
        self.assertEqual(row.accent, ACCENT_OFF)
        self.assertEqual(BADGE_FROZEN, "#4d90e5")

    def test_disconnected_desired_switch_shows_the_auto_on_sublabel(self):
        row = _by_id(_rows("Switches", disconnected=True, desired=frozenset({1})), 1)
        self.assertEqual(row.sublabel, "auto-on for next game launch")

    def test_one_shot_and_master_chips(self):
        rows = _rows("Switches")
        self.assertEqual(_by_id(rows, 2).chip, "one-shot")
        self.assertEqual(_by_id(rows, 7).chip, "master")
        self.assertEqual(_by_id(rows, 1).chip, "")

    def test_value_row_chip_is_the_variable_type(self):
        row = _by_id(_rows("Values"), 3)
        self.assertEqual(row.chip, "4bytes")

    def test_value_text_come_from_the_values_mapping(self):
        rows = build_rows(_entries(), "Values", "", _snap(), 800,
                          values={3: "42"})
        self.assertEqual(_by_id(rows, 3).value_text, "42")

    def test_hit_rects_cover_the_whole_row(self):
        row = _by_id(_rows("Switches"), 1)
        self.assertEqual((row.hit.x, row.hit.w, row.hit.h), (0, 800, 64))
        self.assertTrue(row.hit.contains(799, 63))
        self.assertFalse(row.hit.contains(0, 64))

    def test_info_chip_is_16x16_at_the_right_edge(self):
        switch = _by_id(_rows("Switches"), 1)
        self.assertEqual((switch.info_hit.w, switch.info_hit.h), (16, 16))
        self.assertEqual(switch.info_hit.x, 800 - 24)
        value = _by_id(_rows("Values"), 3)
        self.assertEqual(value.info_hit.x, 800 - 24)

    def test_value_area_hit_spans_240px(self):
        row = _by_id(_rows("Values"), 3)
        self.assertEqual((row.value_area_hit.x, row.value_area_hit.w),
                         (800 - 8 - 240, 240))
        self.assertEqual(row.value_area_hit.h, 72)

    def test_expanded_value_row_is_120px_with_editor_rects(self):
        rows = build_rows(_entries(), "Values", "", _snap(), 800,
                          expanded_values=frozenset({3}))
        row = _by_id(rows, 3)
        self.assertEqual(row.height, 120)
        self.assertTrue(row.expanded)
        editor = row.editor
        self.assertEqual((editor.apply.w, editor.freeze.w), (56, 56))
        self.assertEqual((editor.plus.w, editor.minus.w, editor.reset.w),
                         (48, 48, 48))
        # right-anchored button line with 8 px gaps
        self.assertEqual(editor.reset.x, 800 - 8 - 48)
        self.assertEqual(editor.minus.x, editor.reset.x - 8 - 48)
        self.assertEqual(editor.plus.x, editor.minus.x - 8 - 48)
        self.assertEqual(editor.freeze.x, editor.plus.x - 8 - 56)
        self.assertEqual(editor.apply.x, editor.freeze.x - 8 - 56)
        self.assertEqual(editor.input.x, 8)
        self.assertEqual(editor.input.w, editor.apply.x - 8 - editor.input.x)
        # editor line sits below the collapsed height, 4 px padding
        self.assertEqual(editor.apply.y, row.y + 72 + 4)
        self.assertEqual(editor.apply.h, 120 - 72 - 8)

    def test_build_rows_refuses_a_too_narrow_width(self):
        with self.assertRaises(RowModelError):
            build_rows(_entries(), "Switches", "", _snap(), 319)

    def test_build_rows_refuses_an_unknown_view(self):
        with self.assertRaises(RowModelError):
            build_rows(_entries(), "Bogus", "", _snap(), 800)

    def test_no_rows_when_search_matches_nothing(self):
        self.assertEqual(build_rows(_entries(), "Switches", "zzz", _snap(), 800),
                         [])


class SlicePagesTests(unittest.TestCase):
    """Mixed-content page slicing (floor rule, oversized rows, empty area)."""

    def _row(self, height, entry_id, y=None):
        row = mock.MagicMock()
        row.height = height
        row.entry_id = entry_id
        row.y = 0 if y is None else y
        return row

    def test_floor_accumulation(self):
        rows = [self._row(64, i) for i in range(1, 4)] + [self._row(72, 4)]
        pages = slice_pages(rows, 200)
        self.assertEqual([len(page) for page in pages], [3, 1])
        self.assertEqual(pages[0][0].height, 64)
        self.assertEqual(pages[1][0].entry_id, 4)

    def test_oversized_row_gets_its_own_page(self):
        rows = [self._row(120, 1), self._row(64, 2)]
        pages = slice_pages(rows, 100)
        self.assertEqual(len(pages), 2)
        self.assertEqual([row.entry_id for row in pages[0]], [1])

    def test_zero_area_falls_back_to_one_row_per_page(self):
        rows = [self._row(64, i) for i in range(1, 4)]
        pages = slice_pages(rows, 0)
        self.assertEqual(len(pages), 3)
        self.assertTrue(all(len(page) == 1 for page in pages))

    def test_area_larger_than_the_list_is_one_page(self):
        rows = [self._row(48, 1), self._row(64, 2)]
        pages = slice_pages(rows, 400)
        self.assertEqual(len(pages), 1)

    def test_bad_input_raises(self):
        with self.assertRaises(RowModelError):
            slice_pages("rows", 100)
        with self.assertRaises(RowModelError):
            slice_pages([], -1)


class FindRowTests(unittest.TestCase):
    def _rows(self):
        rows = []
        y = 0
        for entry_id, height in ((1, 48), (2, 64), (3, 72)):
            row = mock.MagicMock()
            row.y, row.height, row.entry_id = y, height, entry_id
            rows.append(row)
            y += height
        return rows

    def test_find_row_by_row_area_coordinate(self):
        rows = self._rows()
        self.assertEqual(find_row(rows, 10).entry_id, 1)   # inside section
        self.assertEqual(find_row(rows, 60).entry_id, 2)   # inside switch
        self.assertEqual(find_row(rows, 120).entry_id, 3)  # inside value
        self.assertIsNone(find_row(rows, 184))             # beyond the last row
        self.assertIsNone(find_row(rows, -1))              # before the first row

    def test_find_row_refuses_non_integer(self):
        with self.assertRaises(RowModelError):
            find_row(self._rows(), "10")

    def test_page_of_entry_finds_the_page_or_none(self):
        import unittest.mock as mock
        rows = []
        y = 0
        for entry_id, height in ((1, 48), (2, 64), (3, 72), (4, 64), (5, 72)):
            row = mock.MagicMock()
            row.y, row.height, row.entry_id = y, height, entry_id
            rows.append(row)
            y += height
        pages = slice_pages(rows, 150)
        from ct2trainer.native.ui_rows import page_of_entry
        self.assertIsNotNone(page_of_entry(pages, 1))
        self.assertEqual(page_of_entry(pages, 999), None)
        with self.assertRaises(RowModelError):
            page_of_entry(pages, "1")


if __name__ == "__main__":
    unittest.main()
