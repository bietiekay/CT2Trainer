"""AP-10 corpus traceability: gap traceability + regression selection tests.

Covers the two new lane tools in tools/corpus_denominator:
  - gap_traceability.py: record-level trace entries, gap reverse index,
    requirement rollup, and consistency cross-checks against the committed
    gap_inventory artifacts.
  - regression_selection.py: deterministic per-capability regression
    selection with status ordering, caps and static-only guarantees.

Inputs (committed, read-only):
  gap_inventory/gap-report.json, gap_inventory/inventory.json,
  tests/fixtures/reference-inventory.json.
No CT file is executed; outputs go to temporary directories only.
"""
import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

import sys

sys.path.insert(0, str(ROOT / "tools" / "corpus_denominator"))

import gap_traceability  # noqa: E402
import regression_selection  # noqa: E402

GAP_REPORT = ROOT / "gap_inventory" / "gap-report.json"
INVENTORY = ROOT / "gap_inventory" / "inventory.json"
REFERENCE = ROOT / "tests" / "fixtures" / "reference-inventory.json"

RUN_ID = "unit-test-deterministic"


def _load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _trace_argv(output):
    return [
        "--gap-report", str(GAP_REPORT),
        "--inventory", str(INVENTORY),
        "--output", str(output),
        "--run-id", RUN_ID,
    ]


def _selection_argv(output, extra):
    return [
        "--gap-report", str(GAP_REPORT),
        "--output", str(output),
        "--run-id", RUN_ID,
        *extra,
    ]


class TraceabilityTests(unittest.TestCase):
    def setUp(self):
        self.report = _load(GAP_REPORT)
        self.inventory = _load(INVENTORY)
        self.out_dir = None

    def tearDown(self):
        if self.out_dir is not None:
            import shutil
            shutil.rmtree(self.out_dir, ignore_errors=True)

    def _run(self, extra=()):
        self.assertIsNotNone(self.out_dir, "call _run_in_tmp first")
        out = Path(self.out_dir) / "out"
        rc = gap_traceability.main(_trace_argv(out) + list(extra))
        self.assertEqual(rc, 0, "gap_traceability.main must return 0")
        document = json.loads((out / "traceability.json").read_text(encoding="utf-8"))
        return document

    def _run_in_tmp(self, extra=()):
        self.out_dir = tempfile.mkdtemp(prefix="lane-corpus-traceability-test-")
        return self._run(extra)

    def test_outputs_are_written_and_deterministic(self):
        base = tempfile.mkdtemp(prefix="lane-corpus-traceability-test-")
        try:
            first = Path(base) / "run-1"
            second = Path(base) / "run-2"
            for target in (first, second):
                rc = gap_traceability.main(_trace_argv(target))
                self.assertEqual(rc, 0)
                artifact = target / "traceability.json"
                self.assertTrue(artifact.is_file())
            self.assertEqual(
                first.joinpath("traceability.json").read_bytes(),
                second.joinpath("traceability.json").read_bytes(),
                "same inputs must produce byte-identical artifacts")
            document = json.loads(
                first.joinpath("traceability.json").read_text(encoding="utf-8"))
            self.assertEqual(document["run_id"], RUN_ID)
            self.assertEqual(document["generated"], "run %s" % RUN_ID)
            self.assertEqual(document["schema"], "corpus-traceability/v1")
        finally:
            import shutil
            shutil.rmtree(base, ignore_errors=True)

    def test_trace_entries_cover_every_pinned_record(self):
        document = self._run_in_tmp()
        entries = document["trace_entries"]
        per_table = {}
        for entry in entries:
            per_table.setdefault(entry["table_path"], []).append(entry)
        for table in self.report["pinned_tables"]:
            self.assertIn(table["path"], per_table)
            self.assertEqual(
                len(per_table[table["path"]]),
                table["counts"]["records"],
                "trace row count must match the report record count for "
                + table["path"])
            for entry in per_table[table["path"]]:
                self.assertEqual(entry["table_sha256"], table["sha256"])
                self.assertEqual(entry["table_path"], table["path"])
                for key in ("record_id", "record_name", "type", "category",
                            "status", "gaps", "providers", "lifetime",
                            "expected_action", "open_apis", "group_breadcrumb"):
                    self.assertIn(key, entry)
        self.assertEqual(set(per_table), {t["path"] for t in self.report["pinned_tables"]})

    def test_expected_action_denominator_pinned(self):
        document = self._run_in_tmp()
        self.assertEqual(document["totals"]["expected_actions"], 6119)
        self.assertEqual(document["totals"]["trace_entries"], 6121)
        self.assertEqual(document["totals"]["navigation_excluded"], 2)
        self.assertEqual(self.report["denominator"]["expected_actions"], 6119)
        self.assertEqual(self.report["denominator"]["records_total"], 6121)

    def test_status_and_category_counts_match_report(self):
        document = self._run_in_tmp()
        consistency = document["consistency"]
        self.assertTrue(consistency["all_ok"])
        by_name = {c["check"]: c for c in consistency["checks"]}
        self.assertTrue(by_name["status_counts"]["ok"])
        self.assertTrue(by_name["category_counts"]["ok"])
        self.assertTrue(by_name["gap_counts_total"]["ok"])
        self.assertEqual(by_name["status_counts"]["actual"],
                         {"locked": 5539, "statically_assumed": 540, "unknown": 42})
        self.assertEqual(by_name["category_counts"]["actual"],
                         {"custom_value": 4, "navigation": 2,
                          "one_shot": 1724, "persistent_script": 466,
                          "string_write": 732, "value_freeze": 3193})

    def test_gap_index_reverse_trace_matches_report_gap_counts(self):
        document = self._run_in_tmp()
        gap_index = document["gap_index"]
        self.assertEqual(gap_index["unmapped_gaps"], [],
                         "every traced gap must carry a gap label")
        report_total = {}
        for table in self.report["pinned_tables"]:
            for gap, count in table["counts"]["gap_counts"].items():
                report_total[gap] = report_total.get(gap, 0) + count
        self.assertEqual(gap_index["gap_counts"], report_total)
        for gap, count in report_total.items():
            entry = gap_index["gaps"][gap]
            self.assertEqual(entry["affected_records"], count)
            traced = sum(len(row["records"]) for row in entry["tables"])
            self.assertEqual(traced, count,
                             "gap %s: per-table record lists must sum to the total" % gap)
            pinned_names = {t["table"] for t in self.report["pinned_tables"]}
            for row in entry["tables"]:
                self.assertIn(row["table"], pinned_names)
                self.assertGreater(len(row["records"]), 0)
        self.assertEqual(gap_index["gap_counts"]["cross_record_symbol"], 3395)
        self.assertEqual(gap_index["gap_counts"]["one_shot_save_contract"], 1724)
        self.assertEqual(gap_index["gap_counts"]["lua_host_profile"], 1918)
        self.assertEqual(gap_index["gap_counts"]["custom_type"], 4)
        self.assertEqual(gap_index["gap_counts"]["lua_clock_speed"], 3)

    def test_trace_entries_carry_open_api_trace(self):
        document = self._run_in_tmp()
        for entry in document["trace_entries"]:
            self.assertEqual(len(entry["open_apis"]), len(entry["gaps"]))
            for api in entry["open_apis"]:
                self.assertFalse(api["unmapped"])
                self.assertIn(api["gap"], entry["gaps"])
                self.assertEqual(api["requirement"],
                                 self.report["gap_labels"][api["gap"]]["requirement"])

    def test_trace_entries_carry_open_api_trace(self):
        document = self._run_in_tmp()
        checked = 0
        for entry in document["trace_entries"]:
            self.assertEqual(len(entry["open_apis"]), len(entry["gaps"]))
            for api in entry["open_apis"]:
                self.assertFalse(api["unmapped"])
                self.assertIn(api["gap"], entry["gaps"])
                self.assertEqual(
                    api["requirement"],
                    self.report["gap_labels"][api["gap"]]["requirement"])
            checked += 1
        self.assertEqual(checked, 6121)

    def test_requirement_index_rolls_up_requirements(self):
        document = self._run_in_tmp()
        requirements = document["requirement_index"]
        self.assertIn("N-16", requirements)
        self.assertIn("N-07", requirements)
        self.assertIn("AP-08 (Global)", requirements)
        # Clock: exactly the three pinned lua_clock_speed records.
        self.assertEqual(requirements["N-16"]["affected_expected_actions"], 3)
        self.assertEqual(requirements["N-16"]["gaps"]["lua_clock_speed"], 3)
        # Global: exactly the nine aa_globalalloc_general records.
        self.assertEqual(requirements["AP-08 (Global)"]["affected_expected_actions"], 9)
        self.assertEqual(requirements["AP-08 (Global)"]["gaps"]["aa_globalalloc_general"], 9)
        # Cross-record symbols belong to N-07 (also lua_symbol_api).
        self.assertEqual(requirements["N-07"]["gaps"]["cross_record_symbol"], 3395)
        # Every requirement row must stay consistent with its status split.
        for req, row in requirements.items():
            total = sum(row["status_counts"].values())
            self.assertLessEqual(row["affected_expected_actions"], total,
                                 "requirement %s: distinct records must not exceed "
                                 "status-weighted occurrences" % req)

    def test_consistency_pins_reference_verification_and_inventory(self):
        document = self._run_in_tmp()
        consistency = document["consistency"]
        by_name = {c["check"]: c for c in consistency["checks"]}
        ref = by_name["reference_pins_all_ok"]
        self.assertTrue(ref["ok"])
        self.assertTrue(by_name["inventory_records_total"]["ok"])
        self.assertTrue(by_name["inventory_expected_actions_total"]["ok"])
        self.assertTrue(by_name["inventory_covers_pinned_shas"]["ok"])
        self.assertTrue(by_name["per_table_counts"]["ok"])
        refs = self.inventory["reference_verification"]
        self.assertEqual(len(refs), 7)
        self.assertTrue(self.inventory["reference_verification_all_ok"])
        fixture = _load(REFERENCE)
        self.assertEqual(set(refs), set(fixture))
        for name, spec in fixture.items():
            self.assertEqual(refs[name]["expected_sha256"], spec["sha256"])
            self.assertEqual(refs[name]["expected_cheat_entries"],
                             spec["cheat_entries"])
            self.assertTrue(refs[name]["hash_match"])
            self.assertTrue(refs[name]["entry_match"])

    def test_refuses_to_write_into_inventory_directory(self):
        self.out_dir = tempfile.mkdtemp(prefix="lane-corpus-traceability-test-")
        rc = gap_traceability.main(_trace_argv(GAP_REPORT.parent))
        self.assertEqual(rc, 3, "output inside the input directory must be refused")
        self.assertFalse((GAP_REPORT.parent / "traceability.json").exists())

    def test_inputs_unchanged_after_run(self):
        before = {_sha256(GAP_REPORT), _sha256(INVENTORY)}
        document = self._run_in_tmp()
        after = {_sha256(GAP_REPORT), _sha256(INVENTORY)}
        self.assertEqual(before, after, "inputs must stay byte-identical")
        self.assertEqual(document["source"]["gap_report_sha256"], _sha256(GAP_REPORT))
        self.assertEqual(document["source"]["inventory_sha256"], _sha256(INVENTORY))


class RegressionSelectionTests(unittest.TestCase):
    def setUp(self):
        self.report = _load(GAP_REPORT)
        self.base_dir = tempfile.mkdtemp(prefix="lane-corpus-selection-test-")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.base_dir, ignore_errors=True)

    def _select(self, extra):
        self._counter = getattr(self, "_counter", 0) + 1
        out = Path(self.base_dir) / ("out-%d" % self._counter)
        rc = regression_selection.main(_selection_argv(out, extra))
        self.assertEqual(rc, 0)
        document = json.loads((out / "regression-selection.json").read_text(encoding="utf-8"))
        return document

    def test_list_prints_all_capabilities(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            rc = regression_selection.main(["--list"])
        self.assertEqual(rc, 0)
        listing = buffer.getvalue()
        for name in regression_selection.CAPABILITIES:
            self.assertIn(name, listing)
        self.assertEqual(len(regression_selection.CAPABILITIES), 12)

    def test_all_selection_is_deterministic_and_capped(self):
        first = self._select(["--all"])
        second = self._select(["--all"])
        self.assertEqual(
            json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))
        self.assertEqual(first["schema"], "corpus-regression-selection/v1")
        self.assertEqual(first["totals"]["capabilities"], 12)
        for name, cap in first["capabilities"].items():
            self.assertLessEqual(cap["selected_count"], 8, name)

    def test_selection_entries_trace_to_report_records(self):
        document = self._select(["--all"])
        by_key = {}
        for table in self.report["pinned_tables"]:
            for group in table["records_by_group"]:
                for rec in group["records"]:
                    by_key[(table["path"], rec["id"])] = rec
        seen = 0
        for cap in document["capabilities"].values():
            for sel in cap["selected"]:
                rec = by_key.get((sel["table_path"], sel["record_id"]))
                self.assertIsNotNone(rec, "selected record must exist in the gap report")
                self.assertEqual(rec["name"], sel["record_name"])
                self.assertEqual(rec["status"], sel["status"])
                self.assertEqual(rec["category"], sel["category"])
                self.assertEqual(sorted(rec["gaps"]), sorted(sel["gaps"]))
                seen += 1
        self.assertEqual(seen, document["totals"]["records_selected"])

    def test_custom_types_selects_all_four_locked_records(self):
        document = self._select(["--capability", "custom_types"])
        cap = document["capabilities"]["custom_types"]
        self.assertEqual(cap["match_total"], 4)
        self.assertEqual(cap["selected_count"], 4)
        self.assertFalse(cap["capped"])
        for sel in cap["selected"]:
            self.assertEqual(sel["category"], "custom_value")
            self.assertEqual(sel["status"], "locked")
            self.assertIn("custom_type", sel["gaps"])

    def test_clock_selection_pins_known_records(self):
        document = self._select(["--capability", "clock"])
        cap = document["capabilities"]["clock"]
        self.assertEqual(cap["match_total"], 3)
        ids = {(sel["table_path"], sel["record_id"]) for sel in cap["selected"]}
        self.assertIn(("case-05.ct", 46), ids)
        self.assertIn(("case-05.ct", 47), ids)
        self.assertIn(("case-06.ct", 17258), ids)
        for sel in cap["selected"]:
            self.assertIn("lua_clock_speed", sel["gaps"])

    def test_ordering_prefers_locked_status(self):
        document = self._select(["--all", "--max-per-capability", "50"])
        rank = regression_selection.STATUS_RANK
        for cap in document["capabilities"].values():
            ranks = [rank[sel["status"]] for sel in cap["selected"]]
            self.assertEqual(ranks, sorted(ranks),
                             "selection must prefer locked records first")

    def test_max_per_capability_caps_selection(self):
        document = self._select(["--capability", "value_freeze",
                                 "--max-per-capability", "2"])
        cap = document["capabilities"]["value_freeze"]
        self.assertEqual(cap["match_total"], 3193)
        self.assertEqual(cap["selected_count"], 2)
        self.assertTrue(cap["capped"])
        self.assertEqual(document["totals"]["records_selected"], 2)

    def test_zero_match_capability_is_visible(self):
        spec = {"description": "test capability without matches",
                "match": {"gaps": ["nonexistent_gap"]}}
        result = regression_selection.select_capability(spec, self.report, 8)
        self.assertEqual(result["match_total"], 0)
        self.assertEqual(result["selected"], [])
        self.assertFalse(result["capped"])

    def test_unknown_capability_is_rejected(self):
        out = Path(self.base_dir) / "out-unknown"
        rc = regression_selection.main(_selection_argv(out, ["--capability", "nope"]))
        self.assertEqual(rc, 2)
        self.assertFalse((out / "regression-selection.json").exists())

    def test_no_capability_selected_is_rejected(self):
        out = Path(self.base_dir) / "out-none"
        rc = regression_selection.main(_selection_argv(out, []))
        self.assertEqual(rc, 2)
        self.assertFalse((out / "regression-selection.json").exists())

    def test_refuses_to_write_into_inventory_directory(self):
        out = Path(self.base_dir) / "regression-selection.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        # Refusal is keyed to the directory of the input artifact.
        argv = _selection_argv(GAP_REPORT.parent, ["--all"])
        rc = regression_selection.main(argv)
        self.assertEqual(rc, 3)
        self.assertFalse((GAP_REPORT.parent / "regression-selection.json").exists())

    def test_selection_is_static_and_input_is_unchanged(self):
        before = _sha256(GAP_REPORT)
        document = self._select(["--all"])
        self.assertEqual(_sha256(GAP_REPORT), before)
        self.assertEqual(document["source"]["gap_report_sha256"], before)
        self.assertIn("no execution of CT Lua/AA", document["note"])


if __name__ == "__main__":
    unittest.main()
