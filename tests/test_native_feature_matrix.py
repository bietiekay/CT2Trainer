"""AP-10 feature matrix: coverage metric and AP-11 exclusion tests.

Covers the lane tool tools/corpus_denominator/feature_matrix.py:
  - feature matrix over the 39 gap classes plus the missing-gates features
  - AP-11 game-gate exclusion (sourced from gap-report missing_gates,
    non-empty, with reasons)
  - pinned coverage state: the feature-weighted goal is reached
  - top-10 priority list is empty (every in-scope feature is covered)
  - consistency cross-checks against the committed gap_inventory artifacts
  - byte-identical reruns with the same run-id

Inputs (committed, read-only):
  gap_inventory/gap-report.json, gap_inventory/inventory.json
No CT file is executed; outputs go to temporary directories only.
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(ROOT / "tools" / "corpus_denominator"))

import feature_matrix  # noqa: E402

GAP_REPORT = ROOT / "gap_inventory" / "gap-report.json"
INVENTORY = ROOT / "gap_inventory" / "inventory.json"

RUN_ID = "unit-test-deterministic"


def _load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _argv(output, extra=()):
    return [
        "--gap-report", str(GAP_REPORT),
        "--inventory", str(INVENTORY),
        "--output", str(output),
        "--run-id", RUN_ID,
        *extra,
    ]


class FeatureMatrixTests(unittest.TestCase):
    def setUp(self):
        self.report = _load(GAP_REPORT)
        self.base = None

    def tearDown(self):
        if self.base is not None:
            shutil.rmtree(self.base, ignore_errors=True)

    def _run_in_tmp(self, extra=()):
        self.base = tempfile.mkdtemp(prefix="lane-feature-matrix-test-")
        out = Path(self.base)
        rc = feature_matrix.main(_argv(out, extra))
        self.assertEqual(rc, 0, "feature_matrix.main must return 0")
        document = json.loads(
            (out / "feature-coverage.json").read_text(encoding="utf-8"))
        self.assertTrue((out / "feature-coverage.json").is_file())
        return document

    def test_outputs_are_written_and_deterministic(self):
        base = tempfile.mkdtemp(prefix="lane-feature-matrix-test-")
        self.addCleanup(shutil.rmtree, base, ignore_errors=True)
        first = Path(base) / "run-1"
        second = Path(base) / "run-2"
        for target in (first, second):
            self.assertEqual(feature_matrix.main(_argv(target)), 0)
            self.assertTrue((target / "feature-coverage.json").is_file())
        self.assertEqual(
            first.joinpath("feature-coverage.json").read_bytes(),
            second.joinpath("feature-coverage.json").read_bytes(),
            "same inputs must produce byte-identical artifacts")
        document = json.loads(
            first.joinpath("feature-coverage.json").read_text(encoding="utf-8"))
        self.assertEqual(document["run_id"], RUN_ID)
        self.assertEqual(document["generated"], "run %s" % RUN_ID)
        self.assertEqual(document["schema"], "corpus-feature-matrix/v1")
        self.assertEqual(document["source"]["gap_report_sha256"],
                         feature_matrix.sha256_file(str(GAP_REPORT)))
        self.assertEqual(document["source"]["inventory_sha256"],
                         feature_matrix.sha256_file(str(INVENTORY)))

    def test_denominator_facts_are_pinned(self):
        document = self._run_in_tmp()
        denom = self.report["denominator"]
        self.assertEqual(denom["expected_actions"], 6025)
        self.assertEqual(denom["confirmed_game_effect_actions"], 0)
        self.assertEqual(
            sum(denom["category_counts"].values()), denom["expected_actions"])
        top = document["consistency"]["checks"]
        by_name = {c["check"]: c for c in top}
        self.assertTrue(by_name["expected_actions"]["ok"])
        self.assertTrue(by_name["confirmed_game_effect_zero"]["ok"])
        self.assertTrue(by_name["category_counts_sum"]["ok"])
        # The pinned top gap is cross_record_symbol with 3377 records.
        self.assertEqual(self.report["top_gaps_pinned"][0]["gap"],
                         "cross_record_symbol")
        self.assertEqual(self.report["top_gaps_pinned"][0]["affected_records"],
                         3377)
        self.assertTrue(by_name["top_gaps_pinned_match"]["ok"])
        matrix = document["feature_matrix"]
        self.assertEqual(matrix["cross_record_symbol"]["affected_records"],
                         3377)

    def test_feature_matrix_covers_every_gap_class_and_gate(self):
        document = self._run_in_tmp()
        matrix = document["feature_matrix"]
        gap_classes = sorted(self.report["gap_labels"])
        for gap in gap_classes:
            self.assertIn(gap, matrix, gap)
            row = matrix[gap]
            self.assertEqual(row["kind"], "gap_class")
            self.assertEqual(row["ap11_excluded"], False)
            self.assertEqual(row["label"],
                             self.report["gap_labels"][gap]["label"])
            self.assertEqual(row["requirement"],
                             self.report["gap_labels"][gap]["requirement"])
        gates = [k for k in matrix if k.startswith("gate:")]
        ap11 = [k for k in matrix if k.startswith("ap11-gate:")]
        self.assertEqual(
            set(matrix),
            set(gap_classes) | set(gates) | set(ap11),
            "matrix keys must be exactly gap classes plus missing-gate rows")
        self.assertEqual(len(gates) + len(ap11),
                         len(self.report["denominator"]["missing_gates"]))

    def test_statuses_are_valid_and_contract_is_complete(self):
        document = self._run_in_tmp()
        for row in document["feature_matrix"].values():
            self.assertIn(row["status"], feature_matrix.VALID_STATUSES)
        self.assertEqual(sorted(feature_matrix.FEATURES),
                         sorted(self.report["gap_labels"]))
        for name, contract in feature_matrix.FEATURES.items():
            self.assertIn(contract["status"], feature_matrix.VALID_STATUSES,
                          name)

    def test_evidence_and_module_paths_exist(self):
        for name, contract in feature_matrix.FEATURES.items():
            for path in contract["evidence"]:
                self.assertTrue((ROOT / path).is_file(),
                                "%s evidence missing: %s" % (name, path))
                self.assertTrue(path.startswith("tests/test_native_"),
                                "%s evidence is not a native test: %s"
                                % (name, path))
            for path in contract["modules"]:
                self.assertTrue((ROOT / path).exists(),
                                "%s module missing: %s" % (name, path))
        for contract in feature_matrix.GATE_FEATURES.values():
            for path in contract["evidence"]:
                self.assertTrue((ROOT / path).is_file(), path)
            for path in contract["modules"]:
                self.assertTrue((ROOT / path).exists(), path)

    def test_ap11_exclusion_list_is_not_empty(self):
        document = self._run_in_tmp()
        exclusions = document["ap11_exclusions"]
        self.assertTrue(exclusions,
                        "AP-11 exclusion list must not be empty")
        self.assertEqual(len(exclusions), 4)
        joined = " | ".join(e["gate"] for e in exclusions)
        for keyword in ("game installs", "game effect", "VM/Clean-PC",
                        "Steam Deck with Proton"):
            self.assertIn(keyword, joined)
        for entry in exclusions:
            self.assertTrue(entry["reason"].startswith("AP-11:"))
            self.assertIn(entry["gate"],
                          self.report["denominator"]["missing_gates"])

    def test_ap11_features_are_excluded_from_coverage(self):
        document = self._run_in_tmp()
        matrix = document["feature_matrix"]
        coverage = document["coverage"]
        excluded = [k for k, v in matrix.items() if v["ap11_excluded"]]
        self.assertEqual(len(excluded), 4)
        self.assertEqual(coverage["features_excluded_ap11"], 4)
        self.assertEqual(coverage["features_total"], 46)
        self.assertEqual(coverage["features_in_scope"], 42)
        self.assertEqual(
            coverage["features_in_scope"] + coverage["features_excluded_ap11"],
            coverage["features_total"])
        for key in excluded:
            self.assertEqual(matrix[key]["requirement"], "AP-11 game gate")

    def test_coverage_goal_reached_and_pins_current_state(self):
        document = self._run_in_tmp()
        coverage = document["coverage"]
        # The official goal metric is the feature-weighted coverage over the
        # 42 in-scope features; the action-weighted metric is a separate
        # lens that reaches 100% once every in-scope gap class is covered.
        self.assertGreaterEqual(
            coverage["feature_weighted_coverage_percent"], 90.0)
        self.assertTrue(coverage["goal_reached"])
        # The gap report's AP-11 runtime-confirmation flag is a separate
        # end goal (0/6025 confirmed real-game actions) and stays
        # "NOT REACHED" until real-game evidence exists.
        self.assertEqual(self.report["denominator"]["goal_90_percent"],
                         "NOT REACHED")
        # Pinned current-state counts (feature-weighted denominator 42).
        self.assertEqual(coverage["features_covered"], 42)
        self.assertEqual(coverage["features_partial"], 0)
        self.assertEqual(coverage["features_missing"], 0)
        # Action weighting over the 39 non-AP-11 gap classes.
        self.assertEqual(coverage["actions_weight_in_scope"], 7369)
        self.assertEqual(coverage["actions_weight_ap11_excluded"], 0)
        self.assertEqual(
            coverage["actions_weight_covered"], 7369)
        self.assertAlmostEqual(
            coverage["feature_weighted_coverage_percent"], 100.0,
            delta=0.01)
        self.assertAlmostEqual(
            coverage["action_weighted_coverage_percent"], 7369 / 7369 * 100,
            delta=0.01)

    def test_top10_priority_is_empty_when_all_in_scope_covered(self):
        document = self._run_in_tmp()
        top10 = document["top10_priority"]
        self.assertEqual(
            top10, [],
            "no in-scope feature may remain open once the gates are covered")

    def test_consistency_checks_all_pass(self):
        document = self._run_in_tmp()
        consistency = document["consistency"]
        self.assertTrue(consistency["all_ok"])
        self.assertEqual(len(consistency["checks"]), 13)
        for check in consistency["checks"]:
            self.assertTrue(check["ok"], check["check"])

    def test_pinned_status_spot_checks(self):
        self.assertEqual(feature_matrix.FEATURES["cross_record_symbol"]
                         ["status"], "covered")
        self.assertEqual(feature_matrix.FEATURES["custom_type"]["status"],
                         "covered")
        self.assertEqual(feature_matrix.FEATURES["lua_host_profile"]
                         ["status"], "covered")
        self.assertEqual(feature_matrix.FEATURES["lua_ce_engine_api"]
                         ["status"], "covered")
        self.assertEqual(feature_matrix.FEATURES["aa_conditional_block"]
                         ["status"], "covered")
        self.assertEqual(feature_matrix.FEATURES["aa_luacall"]["status"],
                         "covered")
        self.assertEqual(feature_matrix.FEATURES["aa_nested_script"]
                         ["status"], "covered")
        self.assertEqual(
            feature_matrix.FEATURES["aa_createthread_threadwait"]["status"],
            "covered")
        self.assertEqual(feature_matrix.FEATURES["aa_protection_control"]
                         ["status"], "covered")
        self.assertEqual(feature_matrix.FEATURES["aa_target_api_binding"]
                         ["status"], "covered")
        self.assertEqual(feature_matrix.FEATURES["aa_debugger_api"]["status"],
                         "covered")
        self.assertEqual(feature_matrix.FEATURES["lua_process_api"]["status"],
                         "covered")
        self.assertEqual(feature_matrix.FEATURES["lua_symbol_api"]
                          ["status"], "covered")
        self.assertEqual(
            feature_matrix.FEATURES["managed_method_resolution"]["status"],
            "covered")
        self.assertEqual(feature_matrix.FEATURES["one_shot_save_contract"]
                         ["status"], "covered")
        self.assertEqual(feature_matrix.FEATURES["string_codepage"]
                         ["status"], "covered")
        self.assertEqual(feature_matrix.FEATURES["aa_sections_incomplete"]
                         ["status"], "covered")
        self.assertEqual(feature_matrix.FEATURES["async_lifecycle"]
                         ["status"], "covered")
        self.assertEqual(feature_matrix.FEATURES["dropdown_link"]["status"],
                         "covered")
        self.assertEqual(feature_matrix.FEATURES["recursive_parent_value"]
                         ["status"], "covered")
        self.assertEqual(feature_matrix.FEATURES["lua_typed_target_call"]
                         ["status"], "covered")

        self.assertEqual(
            feature_matrix.FEATURES["aa_globalalloc_general"]["status"],
            "covered")
        self.assertEqual(feature_matrix.FEATURES["parent_activation"]["status"],
                         "covered")

    def test_cli_list_mode_prints_contract(self):
        import contextlib
        import io
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            self.assertEqual(feature_matrix.main(["--list"]), 0)
        listing = buffer.getvalue()
        self.assertIn("cross_record_symbol", listing)
        self.assertIn("one_shot_save_contract", listing)
        self.assertIn("covered", listing)
        # All static gap-class features are now covered; the three missing-gate
        # rows are dynamic and not part of --list output.
        self.assertNotIn("partial", listing)

    def test_refuses_to_write_into_input_directory(self):
        target = GAP_REPORT.parent / "feature-coverage.json"
        before = target.read_bytes() if target.exists() else None
        rc = feature_matrix.main([
            "--gap-report", str(GAP_REPORT),
            "--inventory", str(INVENTORY),
            "--output", str(GAP_REPORT.parent),
            "--run-id", RUN_ID,
        ])
        self.assertEqual(rc, 3)
        after = target.read_bytes() if target.exists() else None
        self.assertEqual(
            before, after,
            "refused write must not create or modify files in the input "
            "directory")

    def test_missing_input_returns_input_error(self):
        missing = ROOT / "gap_inventory" / "absent-report.json"
        out = Path(tempfile.mkdtemp(prefix="lane-feature-matrix-test-"))
        self.addCleanup(shutil.rmtree, str(out), ignore_errors=True)
        rc = feature_matrix.main([
            "--gap-report", str(missing),
            "--inventory", str(INVENTORY),
            "--output", str(out),
            "--run-id", RUN_ID,
        ])
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
