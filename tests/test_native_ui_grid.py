"""Pure grid contract for the multi-column trainer grid (MT-21, 0.36).

Tk-free coverage of the grid layers in ``ui_rows``: the effective
column clamp (a column never falls below the 320 px width floor), the
column layout (equal widths, the leftover pixels to the leftmost
columns, the byte-stable single column), the top-level unit split
(a section with its children never splits across columns), the
deterministic shortest-column-first flow (ties to the lower column
index) and the grid builder ``build_grid`` - including the
byte-stable one-column path against the single-column ``build_rows``
and the width-baked row rectangles of the multi-column grid.
"""
from __future__ import annotations

import unittest

from ct2trainer.native.ui_layout import (ROW_HEIGHT_SECTION, ROW_HEIGHT_SWITCH,
                                         ROW_HEIGHT_VALUE,
                                         ROW_HEIGHT_VALUE_EXPANDED)
from ct2trainer.native.ui_rows import (COLUMN_GAP, MIN_COLUMN_WIDTH,
                                       ROW_HEIGHT_INFO, Row, RowModelError,
                                       RowRect, RowSnapshot, build_grid,
                                       build_rows, column_layout,
                                       effective_columns, flow_units,
                                       row_units)


def _entries() -> dict:
    """A flat plan fixture covering every row kind the grid renders.

    Row heights: section 48, switch 64, value 72, blocked info 48.
    Top-level units: [1, 2, 3] (section + children, 176 px), [4]
    (64 px), [5] (72 px), [6] (48 px).
    """
    return {
        1: {"id": 1, "label": "Section A", "path": "Section A",
            "parent_id": None, "kind": "heading", "selected": True,
            "supported": True, "reason": "", "parent_activation": [2, 3]},
        2: {"id": 2, "label": "Switch One in A", "path": "a/one",
            "parent_id": 1, "kind": "script", "selected": True,
            "supported": True, "reason": ""},
        3: {"id": 3, "label": "Switch Two in A", "path": "a/two",
            "parent_id": 1, "kind": "script", "selected": True,
            "supported": True, "reason": ""},
        4: {"id": 4, "label": "Top Switch", "path": "top",
            "parent_id": None, "kind": "script", "selected": True,
            "supported": True, "reason": ""},
        5: {"id": 5, "label": "Value Row", "path": "value",
            "parent_id": None, "kind": "value", "selected": True,
            "supported": True, "reason": "", "variable_type": "4bytes"},
        6: {"id": 6, "label": "Blocked Row", "path": "blocked",
            "parent_id": None, "kind": "script", "selected": False,
            "supported": True, "reason": "Not selected"},
    }


def _snap() -> RowSnapshot:
    return RowSnapshot()


class EffectiveColumnsTests(unittest.TestCase):
    def test_min_width_gives_one_column(self):
        for requested in (1, 2, 3):
            self.assertEqual(effective_columns(MIN_COLUMN_WIDTH, requested), 1)

    def test_two_column_threshold(self):
        # Two columns need 2 * 320 + 12 = 652 px.
        self.assertEqual(effective_columns(651, 2), 1)
        self.assertEqual(effective_columns(652, 2), 2)
        self.assertEqual(effective_columns(652, 3), 2)

    def test_three_column_threshold(self):
        # Three columns need 3 * 320 + 2 * 12 = 984 px.
        self.assertEqual(effective_columns(983, 3), 2)
        self.assertEqual(effective_columns(984, 3), 3)

    def test_requested_count_is_the_cap(self):
        self.assertEqual(effective_columns(2000, 1), 1)
        self.assertEqual(effective_columns(2000, 2), 2)
        self.assertEqual(effective_columns(2000, 3), 3)

    def test_bad_width_raises(self):
        for bad in (MIN_COLUMN_WIDTH - 1, "800", None):
            with self.assertRaises(RowModelError):
                effective_columns(bad, 1)

    def test_bad_request_raises(self):
        for bad in (0, 4, "2", None):
            with self.assertRaises(RowModelError):
                effective_columns(800, bad)


class ColumnLayoutTests(unittest.TestCase):
    def test_single_column_byte_stable(self):
        self.assertEqual(column_layout(MIN_COLUMN_WIDTH, 1),
                         ([MIN_COLUMN_WIDTH], [0]))
        self.assertEqual(column_layout(1234, 1), ([1234], [0]))

    def test_two_columns(self):
        self.assertEqual(column_layout(1000, 2), ([494, 494], [0, 506]))

    def test_exact_fit_two(self):
        self.assertEqual(column_layout(652, 2), ([320, 320], [0, 332]))

    def test_three_columns_leftover_goes_to_leftmost(self):
        # 1000 - 2 * 12 = 976 = 3 * 325 + 1: one leftover pixel to col 0.
        self.assertEqual(column_layout(1000, 3),
                         ([326, 325, 325], [0, 338, 675]))

    def test_exact_fit_three(self):
        self.assertEqual(column_layout(984, 3),
                         ([320, 320, 320], [0, 332, 664]))

    def test_columns_fill_the_width_exactly(self):
        for width in range(MIN_COLUMN_WIDTH, 1400, 37):
            for columns in (1, 2, 3):
                col_ws, col_xs = column_layout(width, columns)
                self.assertEqual(
                    sum(col_ws) + COLUMN_GAP * (columns - 1), width, width)
                self.assertEqual(col_xs[0], 0)
                for c in range(columns - 1):
                    self.assertEqual(col_xs[c + 1],
                                     col_xs[c] + col_ws[c] + COLUMN_GAP,
                                     (width, columns, c))
                self.assertEqual(col_xs[-1] + col_ws[-1], width)

    def test_refusals(self):
        for bad_width in (MIN_COLUMN_WIDTH - 1, "800"):
            with self.assertRaises(RowModelError):
                column_layout(bad_width, 1)
        for bad_columns in (0, 4, "2"):
            with self.assertRaises(RowModelError):
                column_layout(800, bad_columns)


class RowUnitsTests(unittest.TestCase):
    def _rows(self):
        return [
            Row(kind="section", entry_id=1, y=0, height=48, indent=0,
                state="off", accent="", tint="", label="S", sublabel="",
                chip="", pill=None, pill_on=False, error_dot=False,
                pulsing=False, confirmed=False, info_hit=None,
                hit=RowRect(0, 0, 800, 48)),
            Row(kind="switch", entry_id=2, y=48, height=64, indent=12,
                state="off", accent="", tint="", label="C", sublabel="",
                chip="", pill=None, pill_on=False, error_dot=False,
                pulsing=False, confirmed=False,
                info_hit=RowRect(700, 72, 24, 24),
                hit=RowRect(0, 48, 800, 64)),
            Row(kind="switch", entry_id=3, y=112, height=64, indent=0,
                state="off", accent="", tint="", label="T", sublabel="",
                chip="", pill=None, pill_on=False, error_dot=False,
                pulsing=False, confirmed=False,
                info_hit=RowRect(700, 136, 24, 24),
                hit=RowRect(0, 112, 800, 64)),
        ]

    def test_split_at_indent_zero(self):
        units = row_units(self._rows())
        self.assertEqual([len(u) for u in units], [2, 1])
        self.assertEqual([r.entry_id for r in units[0]], [1, 2])
        self.assertEqual([r.entry_id for r in units[1]], [3])

    def test_units_cover_every_row_exactly_once(self):
        rows = self._rows()
        flat = [r for unit in row_units(rows) for r in unit]
        self.assertEqual(flat, rows)

    def test_indented_row_without_top_level_unit_raises(self):
        orphan = Row(kind="switch", entry_id=9, y=0, height=64, indent=12,
                     state="off", accent="", tint="", label="O", sublabel="",
                     chip="", pill=None, pill_on=False, error_dot=False,
                     pulsing=False, confirmed=False,
                     info_hit=RowRect(700, 24, 24, 24),
                     hit=RowRect(0, 0, 800, 64))
        with self.assertRaises(RowModelError):
            row_units([orphan])

    def test_not_a_list_raises(self):
        with self.assertRaises(RowModelError):
            row_units("nope")


class FlowUnitsTests(unittest.TestCase):
    def test_shortest_column_first(self):
        self.assertEqual(flow_units([64, 72, 64, 48], 2), [[0, 2], [1, 3]])

    def test_ties_go_to_the_lower_index(self):
        self.assertEqual(flow_units([50, 50, 50], 3), [[0], [1], [2]])

    def test_single_column_keeps_order(self):
        self.assertEqual(flow_units([176, 64, 72, 48], 1), [[0, 1, 2, 3]])

    def test_section_unit_height_keeps_children_together(self):
        # The section unit (176 px) lands alone in the first column; the
        # smaller units fill the second.
        self.assertEqual(flow_units([176, 64, 72, 48], 2),
                         [[0], [1, 2, 3]])
        self.assertEqual(flow_units([176, 64, 72, 48], 3),
                         [[0], [1, 3], [2]])

    def test_refusals(self):
        for bad in (0, 4, "2"):
            with self.assertRaises(RowModelError):
                flow_units([10], bad)
        with self.assertRaises(RowModelError):
            flow_units("nope", 2)


class BuildGridTests(unittest.TestCase):
    def setUp(self):
        self.entries = _entries()
        self.snap = _snap()

    def test_single_column_byte_stable(self):
        rows = build_rows(self.entries, "All", "", self.snap, 800)
        grid = build_grid(self.entries, "All", "", self.snap, 800,
                          columns=1)
        self.assertEqual(grid, [rows])

    def test_single_column_byte_stable_with_options(self):
        for view, search in (("All", ""), ("All", "Top Switch"),
                             ("Switches", "")):
            rows = build_rows(self.entries, view, search, self.snap, 800,
                              expanded_values=frozenset({5}),
                              values={5: "42"})
            grid = build_grid(self.entries, view, search, self.snap, 800,
                              columns=1,
                              expanded_values=frozenset({5}),
                              values={5: "42"})
            self.assertEqual(grid, [rows], (view, search))

    def test_single_column_byte_stable_collapsed(self):
        rows = build_rows(self.entries, "All", "", self.snap, 800,
                          collapsed_sections=frozenset({1}))
        grid = build_grid(self.entries, "All", "", self.snap, 800,
                          columns=1,
                          collapsed_sections=frozenset({1}))
        self.assertEqual(grid, [rows])
        # The collapsed section's children do not render at all.
        self.assertNotIn(2, [r.entry_id for r in rows])

    def test_every_row_present_exactly_once(self):
        reference = [r.entry_id for r in
                     build_rows(self.entries, "All", "", self.snap, 1000)]
        for columns in (2, 3):
            grid = build_grid(self.entries, "All", "", self.snap, 1000,
                              columns=columns)
            flat = sorted(r.entry_id for col in grid for r in col)
            self.assertEqual(flat, sorted(reference), columns)

    def test_sections_never_split_across_columns(self):
        for columns in (2, 3):
            grid = build_grid(self.entries, "All", "", self.snap, 1000,
                              columns=columns)
            col_of = {}
            for c, col in enumerate(grid):
                for row in col:
                    col_of[row.entry_id] = c
            # Section A (1) and both of its children (2, 3) share a column.
            self.assertEqual(col_of[1], col_of[2])
            self.assertEqual(col_of[1], col_of[3])

    def test_deterministic_flow_assignment(self):
        grid2 = build_grid(self.entries, "All", "", self.snap, 1000,
                           columns=2)
        self.assertEqual([[r.entry_id for r in col] for col in grid2],
                         [[1, 2, 3], [4, 5, 6]])
        grid3 = build_grid(self.entries, "All", "", self.snap, 1000,
                           columns=3)
        self.assertEqual([[r.entry_id for r in col] for col in grid3],
                         [[1, 2, 3], [4, 6], [5]])
        # Same input twice - the same grid.
        again = build_grid(self.entries, "All", "", self.snap, 1000,
                           columns=3)
        self.assertEqual(again, grid3)

    def test_column_geometry_matches_the_layout(self):
        for columns in (2, 3):
            grid = build_grid(self.entries, "All", "", self.snap, 1000,
                              columns=columns)
            col_ws, col_xs = column_layout(1000, columns)
            self.assertEqual(len(grid), columns)
            for c, col in enumerate(grid):
                for row in col:
                    self.assertEqual(row.hit.x, col_xs[c], (columns, c))
                    self.assertEqual(row.hit.w, col_ws[c], (columns, c))

    def test_x0_baked_into_the_row_rects(self):
        grid = build_grid(self.entries, "All", "", self.snap, 1000, columns=2)
        col_ws, col_xs = column_layout(1000, 2)
        for c, col in enumerate(grid):
            for row in col:
                self.assertGreaterEqual(row.hit.x, col_xs[c])
                # The row exactly fills its column.
                self.assertEqual(row.hit.x + row.hit.w,
                                 col_xs[c] + col_ws[c])
                if row.info_hit is not None:
                    self.assertGreaterEqual(row.info_hit.x, col_xs[c])
                    self.assertLess(row.info_hit.x + row.info_hit.w,
                                    col_xs[c] + col_ws[c])
        # Column 0 keeps the historical coordinates; column 1 is offset
        # (section rows carry no info chip - compare two switch rows).
        self.assertEqual(grid[0][0].hit.x, 0)
        self.assertEqual(grid[1][0].hit.x, col_xs[1])
        switch0 = next(r for r in grid[0] if r.entry_id == 2)
        switch1 = next(r for r in grid[1] if r.entry_id == 4)
        self.assertGreater(switch1.info_hit.x, switch0.info_hit.x)

    def test_expanded_value_keeps_its_width_independent_height(self):
        single = build_rows(self.entries, "All", "", self.snap, 1000,
                            expanded_values=frozenset({5}))
        grid = build_grid(self.entries, "All", "", self.snap, 1000,
                          columns=2, expanded_values=frozenset({5}))
        single_height = next(r.height for r in single if r.entry_id == 5)
        self.assertEqual(single_height, ROW_HEIGHT_VALUE_EXPANDED)
        for col in grid:
            for row in col:
                if row.entry_id == 5:
                    self.assertEqual(row.height, ROW_HEIGHT_VALUE_EXPANDED)
        # Unexpanded: the plain value height.
        plain = build_grid(self.entries, "All", "", self.snap, 1000,
                           columns=2)
        for col in plain:
            for row in col:
                if row.entry_id == 5:
                    self.assertEqual(row.height, ROW_HEIGHT_VALUE)

    def test_value_text_passes_through_to_the_grid(self):
        grid = build_grid(self.entries, "All", "", self.snap, 1000, columns=2,
                          values={5: "42"})
        value_row = next(r for col in grid for r in col if r.entry_id == 5)
        self.assertEqual(value_row.value_text, "42")

    def test_search_passthrough(self):
        grid = build_grid(self.entries, "All", "Top Switch", self.snap, 1000,
                          columns=2)
        flat = sorted(r.entry_id for col in grid for r in col)
        self.assertEqual(flat, [4])

    def test_no_match_gives_empty_columns(self):
        # 800 px fits only two columns - the request is clamped, not
        # refused; 1000 px fits three.
        grid = build_grid(self.entries, "All", "zzz", self.snap, 800,
                          columns=3)
        self.assertEqual(grid, [[], []])
        wide = build_grid(self.entries, "All", "zzz", self.snap, 1000,
                          columns=3)
        self.assertEqual(wide, [[], [], []])
        single = build_grid(self.entries, "All", "zzz", self.snap, 800,
                            columns=1)
        self.assertEqual(single, [[]])

    def test_hidden_children_subtree_suppressed(self):
        entries = {
            1: {"id": 1, "label": "Hidden Section", "path": "hs",
                "parent_id": None, "kind": "heading", "selected": True,
                "supported": True, "reason": "", "hidden_children": True},
            2: {"id": 2, "label": "Hidden Child", "path": "hs/c",
                "parent_id": 1, "kind": "script", "selected": True,
                "supported": True, "reason": ""},
            3: {"id": 3, "label": "Plain Switch", "path": "plain",
                "parent_id": None, "kind": "script", "selected": True,
                "supported": True, "reason": ""},
        }
        for columns in (1, 2):
            grid = build_grid(entries, "All", "", self.snap, 800,
                              columns=columns)
            flat = sorted(r.entry_id for col in grid for r in col)
            self.assertEqual(flat, [1, 3], columns)

    def test_row_heights_are_the_layout_constants(self):
        rows = build_rows(self.entries, "All", "", self.snap, 800)
        by_id = {r.entry_id: r for r in rows}
        self.assertEqual(by_id[1].height, ROW_HEIGHT_SECTION)
        self.assertEqual(by_id[2].height, ROW_HEIGHT_SWITCH)
        self.assertEqual(by_id[5].height, ROW_HEIGHT_VALUE)
        self.assertEqual(by_id[6].height, ROW_HEIGHT_INFO)

    def test_columns_refused(self):
        for bad in (0, 4, "2", None):
            with self.assertRaises(RowModelError):
                build_grid(self.entries, "All", "", self.snap, 800,
                           columns=bad)


if __name__ == "__main__":
    unittest.main()
