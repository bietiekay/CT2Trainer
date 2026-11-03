"""MT-13 (0.26): the pure waiting-view filter/sort layer (table_filter).

The waiting view of ~151 indexed tables needs search and sort; the
decision layer is pure (no OS access, no index mutation).  These tests
pin the filter contract (casefolded substring over the table name AND
any bound process name, input order preserved) and the sort contract
(name / process / status modes, casefolded relative path as the
universal tie-breaker, unknown modes refused).
"""
from __future__ import annotations

import unittest

from ct2trainer.native.master_trainer.master_state import (
    VIEW_MODES as STATE_VIEW_MODES,
    VIEW_SORT_MODES as STATE_VIEW_SORT_MODES,
)
from ct2trainer.native.master_trainer.table_filter import (
    SORT_MODES,
    UNBOUND_PROCESS_LABEL,
    VIEW_MODES,
    filter_tables,
    group_tables_by_process,
    sort_tables,
)


class _Entry:
    """A minimal TableEntry-shaped stand-in (relative_path + names)."""

    def __init__(self, relative_path, process_names=(), status="ok"):
        self.relative_path = relative_path
        self.process_names = tuple(process_names)
        self.status = status


class FilterTests(unittest.TestCase):
    def setUp(self):
        self.entries = [
            _Entry("Games/Indiana Jones/Great Circle.ct",
                   ("Indiana Jones and the Great Circle.exe",)),
            _Entry("Games/Hades II.ct", ("hades2.exe",)),
            _Entry("Sub/RDR2 (Legacy).ct",
                   ("RDR2.exe", "RDR2legacy.exe")),
            _Entry("overwatch2.ct", ("Overwatch2.exe",)),
            _Entry("empty names.ct", ()),
        ]

    def test_empty_query_is_the_identity(self):
        self.assertEqual(filter_tables(self.entries, ""),
                         list(self.entries))
        self.assertEqual(filter_tables(self.entries, "   \t"),
                         list(self.entries))
        self.assertEqual(filter_tables(self.entries, None),
                         list(self.entries))

    def test_matches_the_table_name_casefolded(self):
        result = filter_tables(self.entries, "indiana")
        self.assertEqual([e.relative_path for e in result],
                         ["Games/Indiana Jones/Great Circle.ct"])

    def test_matches_a_bound_process_name(self):
        # No table is *named* "rdr2"; the bound process names match.
        result = filter_tables(self.entries, "rdr2")
        self.assertEqual([e.relative_path for e in result],
                         ["Sub/RDR2 (Legacy).ct"])

    def test_any_bound_name_matching_counts(self):
        result = filter_tables(self.entries, "legacy")
        self.assertEqual([e.relative_path for e in result],
                         ["Sub/RDR2 (Legacy).ct"])

    def test_multi_word_query_is_a_plain_substring(self):
        # The query is not tokenized: it must appear verbatim (casefolded)
        # in the table path or in a single bound name.
        entries = [
            _Entry("one alpha.ct", ("gamma beta.exe",)),
            _Entry("Games/Indiana Jones/Great Circle.ct",
                   ("Indiana Jones and the Great Circle.exe",)),
        ]
        self.assertEqual(len(filter_tables(entries, "great circle")), 1)
        # Reversed order matches no single name verbatim.
        self.assertEqual(filter_tables(entries, "circle great"), [])
        # "one gamma" would match under a tokenized search (one in the
        # path, gamma in the name); the plain substring matches nothing.
        self.assertEqual(filter_tables(entries, "one gamma"), [])

    def test_no_match_yields_an_empty_list(self):
        self.assertEqual(filter_tables(self.entries, "not-a-table"), [])

    def test_unicode_is_casefolded(self):
        entries = [_Entry("Überfall.ct", ("Ueberspiel.exe",))]
        self.assertEqual(len(filter_tables(entries, "über")), 1)
        self.assertEqual(len(filter_tables(entries, "üBer")), 1)
        # The German casefold also catches the plain-ascii form.
        self.assertEqual(len(filter_tables(entries, "ueber")), 1)

    def test_input_order_is_preserved(self):
        shuffled = [self.entries[3], self.entries[1], self.entries[0],
                    self.entries[2], self.entries[4]]
        result = filter_tables(shuffled, ".ct")
        self.assertEqual([e.relative_path for e in result],
                         [e.relative_path for e in shuffled])

    def test_a_table_with_no_names_only_matches_by_name(self):
        self.assertEqual(len(filter_tables(self.entries, "empty names")), 1)
        self.assertEqual(filter_tables(self.entries, "noname.exe"), [])


class SortTests(unittest.TestCase):
    def setUp(self):
        self.entries = [
            _Entry("zeta.ct", ("ZGame.exe",)),
            _Entry("alpha.ct", ("aGame.exe",)),
            _Entry("Beta (Old).ct", ("bgame.exe",)),
            _Entry("broken.ct", (), status="unreadable"),
            _Entry("alpha2.ct", ("aGame.exe",)),
            _Entry("unamed.ct", ()),
        ]

    def test_name_mode_is_casefolded_with_path_tie_break(self):
        result = sort_tables(self.entries, "name")
        self.assertEqual([e.relative_path for e in result],
                         ["alpha.ct", "alpha2.ct", "Beta (Old).ct",
                          "broken.ct", "unamed.ct", "zeta.ct"])

    def test_process_mode_sorts_by_first_bound_name(self):
        result = sort_tables(self.entries, "process")
        self.assertEqual([e.relative_path for e in result],
                         ["alpha.ct", "alpha2.ct",          # aGame
                          "Beta (Old).ct",                  # bgame
                          "zeta.ct",                        # ZGame
                          "broken.ct", "unamed.ct"])        # unbound last

    def test_status_mode_puts_unreadable_last(self):
        result = sort_tables(self.entries, "status")
        self.assertEqual([e.relative_path for e in result],
                         ["alpha.ct", "alpha2.ct", "Beta (Old).ct",
                          "unamed.ct", "zeta.ct", "broken.ct"])

    def test_sort_is_deterministic_on_equal_keys(self):
        entries = [_Entry("b/b.ct"), _Entry("a/b.ct"), _Entry("c/b.ct")]
        first = [e.relative_path for e in sort_tables(entries, "name")]
        for _ in range(3):
            self.assertEqual([e.relative_path for e in
                              sort_tables(entries, "name")], first)

    def test_unknown_mode_is_refused(self):
        with self.assertRaises(ValueError):
            sort_tables(self.entries, "size")

    def test_sort_does_not_mutate_the_input(self):
        order = [e.relative_path for e in self.entries]
        sort_tables(self.entries, "status")
        self.assertEqual([e.relative_path for e in self.entries], order)

    def test_filter_after_sort_composition(self):
        # The documented composition: filter(sort(index.tables(), mode)).
        # "game" hits aGame, bgame and ZGame (never the table names).
        result = filter_tables(sort_tables(self.entries, "process"), "game")
        self.assertEqual([e.relative_path for e in result],
                         ["alpha.ct", "alpha2.ct", "Beta (Old).ct",
                          "zeta.ct"])

    def test_sort_modes_tuple_is_stable(self):
        self.assertEqual(SORT_MODES, ("name", "process", "status"))


class GroupByProcessTests(unittest.TestCase):
    """MT-17 (0.27): the pure process-grouping reshaping."""

    def setUp(self):
        self.entries = [
            _Entry("Games/Indiana Jones/Great Circle.ct",
                   ("Indiana Jones and the Great Circle.exe",)),
            _Entry("Sub/RDR2 (Legacy).ct",
                   ("RDR2.exe", "RDR2legacy.exe")),
            _Entry("hades.ct", ("hades2.exe",)),
            _Entry("empty names.ct", ()),
        ]

    def test_groups_by_each_bound_name(self):
        groups = dict(group_tables_by_process(self.entries))
        self.assertEqual(set(groups),
                         {"hades2.exe",
                          "indiana jones and the great circle.exe",
                          "rdr2.exe", "rdr2legacy.exe",
                          UNBOUND_PROCESS_LABEL})

    def test_a_multi_bound_table_appears_in_each_group(self):
        groups = dict(group_tables_by_process(self.entries))
        rdr2 = self.entries[1]
        self.assertIn(rdr2, groups["rdr2.exe"])
        self.assertIn(rdr2, groups["rdr2legacy.exe"])

    def test_bound_groups_sort_casefolded_and_unbound_last(self):
        order = [label for label, _ in
                 group_tables_by_process(self.entries)]
        self.assertEqual(order,
                         ["hades2.exe",
                          "indiana jones and the great circle.exe",
                          "rdr2.exe", "rdr2legacy.exe",
                          UNBOUND_PROCESS_LABEL])

    def test_within_group_input_order_is_preserved(self):
        entries = [
            _Entry("two.ct", ("b.exe",)),
            _Entry("one.ct", ("b.exe",)),
            _Entry("zero.ct", ("a.exe",)),
        ]
        groups = dict(group_tables_by_process(entries))
        self.assertEqual([e.relative_path for e in groups["b.exe"]],
                         ["two.ct", "one.ct"])
        self.assertEqual([e.relative_path for e in groups["a.exe"]],
                         ["zero.ct"])

    def test_grouping_preserves_the_row_set(self):
        # The documented composition: group(filter(sort(entries, mode))).
        # Every row appears exactly as often as it has bound names (one
        # for the unbound row); nothing is added or dropped.
        rows = filter_tables(sort_tables(self.entries, "name"), "")
        grouped = [e for _, group in group_tables_by_process(rows)
                   for e in group]
        self.assertEqual(len(grouped),
                         sum(len(e.process_names) or 1
                             for e in rows))

    def test_empty_input_yields_no_groups(self):
        self.assertEqual(group_tables_by_process([]), [])

    def test_only_unbound_tables_yield_the_single_unbound_group(self):
        entries = [_Entry("a.ct", ()), _Entry("b.ct", ())]
        groups = group_tables_by_process(entries)
        self.assertEqual([label for label, _ in groups],
                         [UNBOUND_PROCESS_LABEL])
        self.assertEqual(len(groups[0][1]), 2)

    def test_view_modes_tuple_is_stable(self):
        self.assertEqual(VIEW_MODES, ("list", "process"))
        # MT-16: the state document's format-level constants mirror the
        # pure layer (the attach-mode pattern).
        self.assertEqual(VIEW_MODES, STATE_VIEW_MODES)
        self.assertEqual(SORT_MODES, STATE_VIEW_SORT_MODES)


if __name__ == "__main__":
    unittest.main()
