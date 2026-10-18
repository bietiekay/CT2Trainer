"""AP-11 campaign plan and report ingestion tests.

Covers the lane tool tools/corpus_denominator/ap11_campaign.py:
  - manifest: byte-identical reruns, the 23 pinned tables, the 6092-action
    denominator, category counts against the gap report, process
    candidates versus the owned process_detect on the actual CT bytes,
    the fixed priority convention, the per-record map, CT integrity
    failures (missing/tampered), write refusal
  - report: valid ingestion, duplicate idempotency (intra-file and
    re-ingestion), foreign record rejection, confirmed observations
    without evidence_note or game_build_id rejection, empty report,
    schema/table/action violations, replacement and state mismatch

Inputs (committed, read-only):
  gap_inventory/gap-report.json, gap_inventory/inventory.json,
  gap_inventory/feature-coverage.json, gap_inventory/ap11-campaign.json,
  TableReferences/ (CT bytes are read and hashed only, never executed)
No game or process is started; outputs go to temporary directories only.
"""
import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(ROOT / "tools" / "corpus_denominator"))
sys.path.insert(0, str(ROOT / "src"))

import ap11_campaign  # noqa: E402

from ct2trainer.native import process_detect  # noqa: E402

GAP_REPORT = ROOT / "gap_inventory" / "gap-report.json"
INVENTORY = ROOT / "gap_inventory" / "inventory.json"
FEATURE_COVERAGE = ROOT / "gap_inventory" / "feature-coverage.json"
COMMITTED_CAMPAIGN = ROOT / "gap_inventory" / "ap11-campaign.json"
CORPUS_ROOT = ROOT / "TableReferences"

RUN_ID = "unit-test-deterministic"


def _load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f)


def _manifest_argv(output, extra=()):
    return [
        "manifest",
        "--gap-report", str(GAP_REPORT),
        "--inventory", str(INVENTORY),
        "--feature-coverage", str(FEATURE_COVERAGE),
        "--corpus-root", str(CORPUS_ROOT),
        "--output", str(output),
        "--run-id", RUN_ID,
        *extra,
    ]


def _report_argv(report, output, campaign=COMMITTED_CAMPAIGN):
    return [
        "report",
        "--report", str(report),
        "--campaign", str(campaign),
        "--output", str(output),
        "--run-id", RUN_ID,
    ]


def _report_doc(table="case-01.ct", observations=(), game_build_id="Build367",
                process_name="ct2synth01.exe", process_pid=4242,
                schema=ap11_campaign.REPORT_SCHEMA):
    doc = {
        "schema": schema,
        "table": table,
        "process_name": process_name,
        "process_pid": process_pid,
        "game_build_id": game_build_id,
        "observations": list(observations),
    }
    return doc


def _obs(record_id=121, action="persistent_script", confirmed=False,
         evidence_note=None, expected="script enabled and held",
         observed="script enabled, symbol registered"):
    return {
        "record_id": record_id,
        "action": action,
        "expected": expected,
        "observed": observed,
        "confirmed": confirmed,
        "evidence_note": evidence_note,
    }


class _Base(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="lane-ap11-campaign-test-"))

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def _report_file(self, doc, name="report.json", subdir="input"):
        parent = self.base / subdir
        parent.mkdir(parents=True, exist_ok=True)
        path = parent / name
        _write_json(path, doc)
        return path

    def _run_manifest(self, output, extra=()):
        rc = ap11_campaign.main(_manifest_argv(output, extra))
        document = json.loads((output / "ap11-campaign.json").read_text(encoding="utf-8"))
        return rc, document


class ManifestTests(_Base):
    def test_manifest_two_runs_are_byte_identical(self):
        first = self.base / "run-1"
        second = self.base / "run-2"
        rc1, document = self._run_manifest(first)
        rc2, _ = self._run_manifest(second)
        self.assertEqual(rc1, 0)
        self.assertEqual(rc2, 0)
        self.assertEqual(
            (first / "ap11-campaign.json").read_bytes(),
            (second / "ap11-campaign.json").read_bytes(),
            "same inputs must produce byte-identical campaign manifests")
        self.assertEqual(document["schema"], "ap11-campaign/v1")
        self.assertEqual(document["run_id"], RUN_ID)
        self.assertEqual(document["generated"], "run %s" % RUN_ID)

    def test_manifest_contains_fourteen_pinned_tables(self):
        _, document = self._run_manifest(self.base / "out")
        report = _load(GAP_REPORT)
        self.assertEqual(document["totals"]["tables"], 23)
        self.assertEqual(document["denominator"]["unique_tables"], 23)
        self.assertEqual(len(document["tables"]), 23)
        self.assertEqual([t["name"] for t in document["tables"]],
                         [t["table"] for t in report["pinned_tables"]])
        for table, source in zip(document["tables"], report["pinned_tables"]):
            self.assertEqual(table["ct_path"], source["path"])
            self.assertEqual(table["ct_sha256"], source["sha256"])
            self.assertEqual(table["architecture"], source["architecture"]["value"])
            self.assertEqual(table["expected_actions"],
                             source["counts"]["expected_actions"])

    def test_manifest_expected_actions_sum_is_6092(self):
        _, document = self._run_manifest(self.base / "out")
        self.assertEqual(document["totals"]["expected_actions"], 6092)
        self.assertEqual(document["denominator"]["expected_actions"], 6092)
        self.assertEqual(document["denominator"]["confirmed_game_effect_actions"], 0)
        self.assertEqual(sum(t["expected_actions"] for t in document["tables"]), 6092)

    def test_manifest_category_counts_match_gap_report(self):
        _, document = self._run_manifest(self.base / "out")
        report = _load(GAP_REPORT)
        denom = report["denominator"]["category_counts"]
        self.assertEqual(document["totals"]["category_counts"], denom)
        self.assertEqual(denom, {"custom_value": 4, "navigation": 2,
                                 "one_shot": 1723, "persistent_script": 452,
                                 "string_write": 732, "value_freeze": 3181})
        for table, source in zip(document["tables"], report["pinned_tables"]):
            self.assertEqual(table["category_counts"],
                             {c: n for c, n in source["counts"]["categories"].items()
                              if c in ap11_campaign.CATEGORY_PRIORITY},
                             table["ct_path"])
            self.assertEqual(sum(table["category_counts"].values()),
                             table["expected_actions"], table["ct_path"])
        self.assertTrue(document["consistency"]["all_ok"])

    def test_manifest_process_candidates_match_process_detect_on_ct_bytes(self):
        _, document = self._run_manifest(self.base / "out")
        for table in document["tables"]:
            data = (CORPUS_ROOT / table["ct_path"]).read_bytes()
            self.assertEqual(table["process_candidates"],
                             process_detect.find_candidates(data),
                             table["ct_path"])
        by_name = {t["name"]: t for t in document["tables"]}
        self.assertEqual(by_name["case-01.ct"]["process_candidates"],
                         ["ct2synth01.exe"])
        self.assertEqual(by_name["case-07.ct"]["process_candidates"],
                         ["ct2synth07.exe"])
        self.assertEqual(by_name["case-05.ct"]["process_candidates"],
                         ["ct2synth05.exe"])

    def test_manifest_priority_order_follows_fixed_convention(self):
        _, document = self._run_manifest(self.base / "out")
        fixed = list(ap11_campaign.CATEGORY_PRIORITY)
        self.assertEqual(fixed, ["value_freeze", "string_write", "one_shot",
                                 "persistent_script", "custom_value"])
        for table in document["tables"]:
            expected_order = [c for c in fixed
                              if table["category_counts"].get(c, 0) > 0]
            self.assertEqual(table["priority_order"], expected_order,
                             table["ct_path"])
        by_name = {t["name"]: t for t in document["tables"]}
        self.assertEqual(by_name["case-06.ct"]["priority_order"],
                         ["value_freeze", "persistent_script", "custom_value"])
        self.assertEqual(by_name["case-07.ct"]["priority_order"],
                         ["value_freeze", "string_write", "one_shot",
                          "persistent_script"])
        self.assertEqual(by_name["case-05.ct"]["priority_order"],
                         ["persistent_script"])

    def test_manifest_record_map_covers_every_expected_action(self):
        _, document = self._run_manifest(self.base / "out")
        report = _load(GAP_REPORT)
        for table, source in zip(document["tables"], report["pinned_tables"]):
            record_map = {}
            for group in source["records_by_group"]:
                for rec in group["records"]:
                    record_map[str(rec["id"])] = rec["category"]
            self.assertEqual(table["records"], record_map, table["ct_path"])
            self.assertEqual(len(table["records"]),
                             table["expected_actions"] + table["navigation_excluded"],
                             table["ct_path"])

    def _synthetic_corpus(self, sub, tamper=False, omit_ct=False):
        """Build a minimal consistent input set with one pinned table."""
        corpus = self.base / sub / "corpus"
        corpus.mkdir(parents=True, exist_ok=True)
        ct = corpus / "syn.ct"
        original = (b"<CheatTable><CheatEntries>"
                    b"<CheatEntry><Description>syn.exe</Description>"
                    b"</CheatEntry></CheatEntries></CheatTable>")
        file_bytes = original + (b"\x00tampered" if tamper else b"")
        if not omit_ct:
            ct.write_bytes(file_bytes)
        # The gap report pins the untampered original; a tampered file on
        # disk therefore disagrees with the pinned SHA.
        expected_sha = hashlib.sha256(original).hexdigest()
        table = {
            "architecture": {"signals": ["module:syn.exe"], "value": "x64"},
            "counts": {
                "categories": {"value_freeze": 1},
                "entries_total": 1, "expected_actions": 1, "gap_counts": {},
                "group_toggle_actions": 0, "groups": 0,
                "navigation_excluded": 0, "record_types": {"value": 1},
                "records": 1, "status_counts": {"locked": 1},
            },
            "duplicate_ids": {}, "format_version": "45", "groups": [],
            "main_initialization": None, "path": "syn.ct",
            "paths": ["syn.ct"],
            "records_by_group": [{"group": "[root]", "records": [
                {"address_kind": "fixed", "architecture": "x64",
                 "async": None, "category": "value_freeze", "depth": 1,
                 "gaps": [], "id": 7,
                 "lifetime": "read_write_freezable_value", "name": "hp",
                 "parent": "[root]", "providers": ["typed_value_readwrite"],
                 "semantics": "4 Bytes value", "status": "locked",
                 "target_build": "build_bound_fixed_address", "type": "value"}]}],
            "sha256": expected_sha, "size_bytes": len(original),
            "table": "Syn", "table_flags": {}, "top_gaps": [],
        }
        gap_report = {
            "generated": "synthetic", "run_id": "synthetic",
            "lane": "synthetic", "counting_convention": {},
            "gap_labels": {}, "pinned_tables": [table], "corpus_rest": {},
            "denominator": {
                "category_counts": {"value_freeze": 1},
                "confirmed_game_effect_actions": 0,
                "confirmed_percent": 0.0, "expected_actions": 1,
                "goal_90_percent": "NOT REACHED",
                "group_toggle_actions": 0, "groups_total": 0,
                "missing_gates": [], "navigation_excluded": 0,
                "record_types": {"value": 1}, "records_total": 1,
                "scope": "synthetic", "separation": {},
                "status_counts": {"locked": 1}, "unique_tables": 1,
            },
            "top_gaps_pinned": [],
        }
        inventory = {"generated": "synthetic", "run_id": "synthetic",
                     "tables": [{"sha256": expected_sha,
                                 "paths": ["syn.ct"]}],
                     "totals": {"records": 1}}
        coverage = {"schema": "corpus-feature-matrix/v1",
                    "consistency": {"all_ok": True, "checks": [
                        {"check": "expected_actions", "ok": True,
                         "expected": 1, "actual": 1},
                        {"check": "pinned_shas_in_inventory", "ok": True,
                         "expected": [expected_sha], "actual": [expected_sha]}]}}
        sub_root = self.base / sub
        _write_json(sub_root / "gap-report.json", gap_report)
        _write_json(sub_root / "inventory.json", inventory)
        _write_json(sub_root / "feature-coverage.json", coverage)
        return sub_root

    def test_manifest_tampered_ct_fails_consistency(self):
        sub = self._synthetic_corpus("tampered", tamper=True)
        out = self.base / "tampered-out"
        rc = ap11_campaign.main([
            "manifest", "--gap-report", str(sub / "gap-report.json"),
            "--inventory", str(sub / "inventory.json"),
            "--feature-coverage", str(sub / "feature-coverage.json"),
            "--corpus-root", str(sub / "corpus"),
            "--output", str(out), "--run-id", RUN_ID])
        self.assertEqual(rc, 2, "tampered CT bytes must fail consistency")
        document = json.loads((out / "ap11-campaign.json").read_text(
            encoding="utf-8"))
        by_name = {c["check"]: c for c in document["consistency"]["checks"]}
        self.assertFalse(by_name["ct_sha_integrity"]["ok"])
        self.assertFalse(document["consistency"]["all_ok"])

    def test_manifest_missing_ct_is_input_error(self):
        sub = self._synthetic_corpus("missing-ct", omit_ct=True)
        out = self.base / "missing-ct-out"
        rc = ap11_campaign.main([
            "manifest", "--gap-report", str(sub / "gap-report.json"),
            "--inventory", str(sub / "inventory.json"),
            "--feature-coverage", str(sub / "feature-coverage.json"),
            "--corpus-root", str(sub / "corpus"),
            "--output", str(out), "--run-id", RUN_ID])
        self.assertEqual(rc, 1, "missing pinned CT must be an input error")
        self.assertFalse((out / "ap11-campaign.json").exists())

    def test_manifest_refuses_to_write_into_input_directories(self):
        baseline = GAP_REPORT.parent / "ap11-campaign.json"
        before = (baseline.read_bytes()
                  if baseline.is_file() else None)
        rc = ap11_campaign.main(_manifest_argv(GAP_REPORT.parent, [
            "--gap-report", str(GAP_REPORT),
            "--inventory", str(INVENTORY),
            "--feature-coverage", str(FEATURE_COVERAGE)]))
        self.assertEqual(rc, 3)
        after = baseline.read_bytes() if baseline.is_file() else None
        self.assertEqual(before, after,
                         "a refused run must not touch the input directory")
        # Refusal also covers the read-only corpus root.
        sub = self._synthetic_corpus("refused-corpus")
        rc = ap11_campaign.main([
            "manifest", "--gap-report", str(sub / "gap-report.json"),
            "--inventory", str(sub / "inventory.json"),
            "--feature-coverage", str(sub / "feature-coverage.json"),
            "--corpus-root", str(sub / "corpus"),
            "--output", str(sub / "corpus"), "--run-id", RUN_ID])
        self.assertEqual(rc, 3, "writing into the corpus root must be refused")

    def test_manifest_missing_input_is_input_error(self):
        out = self.base / "missing-input"
        rc = ap11_campaign.main(_manifest_argv(out, [
            "--gap-report", str(self.base / "absent-report.json")]))
        self.assertEqual(rc, 1)
        self.assertFalse((out / "ap11-campaign.json").exists())

    def test_committed_manifest_is_byte_reproducible(self):
        self.assertTrue(COMMITTED_CAMPAIGN.is_file(),
                        "committed campaign baseline must exist")
        committed = _load(COMMITTED_CAMPAIGN)
        run_id = committed["run_id"]
        out = self.base / "committed-repro"
        rc = ap11_campaign.main([
            "manifest", "--gap-report", str(GAP_REPORT),
            "--inventory", str(INVENTORY),
            "--feature-coverage", str(FEATURE_COVERAGE),
            "--corpus-root", str(CORPUS_ROOT),
            "--output", str(out), "--run-id", run_id])
        self.assertEqual(rc, 0)
        self.assertEqual(
            (out / "ap11-campaign.json").read_bytes(),
            COMMITTED_CAMPAIGN.read_bytes(),
            "committed baseline must be byte-identical to a fresh run")

    def test_manifest_list_mode_prints_plan_without_writing(self):
        import contextlib
        import io
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            rc = ap11_campaign.main([
                "manifest", "--gap-report", str(GAP_REPORT),
                "--inventory", str(INVENTORY),
                "--feature-coverage", str(FEATURE_COVERAGE),
                "--corpus-root", str(CORPUS_ROOT), "--list"])
        self.assertEqual(rc, 0)
        listing = buffer.getvalue()
        for name in ("case-01.ct", "case-07.ct", "case-06.ct", "case-13.ct",
                     "case-14.ct"):
            self.assertIn(name, listing)
        self.assertIn("value_freeze", listing)


class ReportIngestionTests(_Base):
    def _ingest(self, doc, out_name="ingest", name="report.json"):
        report = self._report_file(doc, name)
        out = self.base / out_name
        rc = ap11_campaign.main(_report_argv(report, out))
        summary = None
        state = None
        if rc == 0:
            summary = json.loads((out / "ap11-summary.json").read_text(
                encoding="utf-8"))
            state = json.loads((out / "ap11-progress.json").read_text(
                encoding="utf-8"))
        return rc, summary, state, report, out

    def test_report_valid_ingest_writes_state_and_summary(self):
        doc = _report_doc(observations=[
            _obs(record_id=121, action="persistent_script", confirmed=True,
                 evidence_note="held patch readback after ON"),
            _obs(record_id=122, action="value_freeze", confirmed=True,
                 evidence_note="value stable at 100 over damage ticks"),
            _obs(record_id=148, action="persistent_script", confirmed=False,
                 evidence_note=None),
        ])
        rc, summary, state, _, _ = self._ingest(doc)
        self.assertEqual(rc, 0)
        self.assertEqual(summary["schema"], "ap11-summary/v1")
        self.assertEqual(state["schema"], "ap11-progress/v1")
        trine = summary["tables"]["case-01.ct"]
        self.assertEqual(trine["report_ingested"], True)
        self.assertEqual(trine["confirmed_by_category"],
                         {"persistent_script": 1, "value_freeze": 1})
        self.assertEqual(trine["confirmed_total"], 2)
        self.assertEqual(trine["expected_actions"], 103)
        self.assertEqual(trine["process_name"], "ct2synth01.exe")
        self.assertEqual(trine["process_pid"], 4242)
        self.assertEqual(trine["game_build_id"], "Build367")
        overall = summary["overall"]
        self.assertEqual(overall["expected_actions"], 6092)
        self.assertEqual(overall["confirmed_actions"], 2)
        self.assertEqual(overall["remaining_actions"], 6090)
        self.assertAlmostEqual(overall["confirmed_percent"],
                               100.0 * 2 / 6092, places=2)
        self.assertFalse(overall["goal_reached"])
        # Every campaign table stays visible with its own expected share.
        self.assertEqual(len(summary["tables"]), 23)
        self.assertEqual(summary["tables"]["case-13.ct"]["expected_actions"], 1)
        self.assertEqual(summary["tables"]["case-23.ct"]["expected_actions"], 3)
        self.assertEqual(summary["tables"]["case-13.ct"]["confirmed_total"], 0)
        self.assertEqual(summary["tables"]["case-14.ct"]["expected_actions"], 44)
        self.assertEqual(summary["tables"]["case-14.ct"]["confirmed_total"], 0)
        self.assertEqual(summary["tables"]["case-18.ct"]["expected_actions"], 18)
        self.assertEqual(summary["tables"]["case-18.ct"]["confirmed_total"], 0)
        self.assertEqual(summary["tables"]["case-23.ct"]["expected_actions"], 3)
        self.assertEqual(summary["tables"]["case-23.ct"]["confirmed_total"], 0)
        self.assertEqual(summary["tables"]["case-21.ct"]["expected_actions"], 5)
        self.assertEqual(summary["tables"]["case-21.ct"]["confirmed_total"], 0)
        self.assertEqual(summary["tables"]["case-22.ct"]["expected_actions"], 4)
        self.assertEqual(summary["tables"]["case-22.ct"]["confirmed_total"], 0)
        self.assertEqual(summary["ingestion"]["observations_accepted"], 3)
        self.assertEqual(summary["ingestion"]["duplicates_removed"], 0)
        self.assertEqual(summary["ingestion"]["replaced_previous"], False)

    def test_report_reingest_same_file_is_idempotent(self):
        doc = _report_doc(observations=[
            _obs(record_id=121, action="persistent_script", confirmed=True,
                 evidence_note="held patch readback after ON"),
        ])
        rc1, summary1, state1, report, out = self._ingest(doc)
        self.assertEqual(rc1, 0)
        first_state = (out / "ap11-progress.json").read_bytes()
        first_summary = (out / "ap11-summary.json").read_bytes()
        rc2, summary2, state2, _, _ = self._ingest(doc)
        self.assertEqual(rc2, 0)
        self.assertEqual((out / "ap11-progress.json").read_bytes(),
                         first_state, "re-ingesting the same report file "
                                       "must be a byte-identical no-op")
        self.assertEqual((out / "ap11-summary.json").read_bytes(),
                         first_summary)
        self.assertEqual(summary2["ingestion"]["replaced_previous"], False)
        self.assertEqual(summary2["overall"]["confirmed_actions"], 1)
        self.assertEqual(state2["tables"]["case-01.ct"]["observations"],
                         state1["tables"]["case-01.ct"]["observations"])

    def test_report_intra_file_duplicates_are_idempotent(self):
        doc = _report_doc(observations=[
            _obs(record_id=122, action="value_freeze", confirmed=False,
                 evidence_note=None, expected="first unconfirmed attempt",
                 observed="no effect observed"),
            _obs(record_id=122, action="value_freeze", confirmed=True,
                 evidence_note="second attempt confirmed",
                 expected="second attempt", observed="value frozen"),
        ])
        rc, summary, state, _, _ = self._ingest(doc)
        self.assertEqual(rc, 0)
        self.assertEqual(summary["ingestion"]["observations_total"], 2)
        self.assertEqual(summary["ingestion"]["observations_accepted"], 1)
        self.assertEqual(summary["ingestion"]["duplicates_removed"], 1)
        obs = state["tables"]["case-01.ct"]["observations"]
        self.assertEqual(len(obs), 1)
        self.assertTrue(obs[0]["confirmed"],
                        "a confirmed duplicate must win over the "
                        "unconfirmed one")
        self.assertEqual(summary["tables"]["case-01.ct"]["confirmed_total"], 1)
        # Adding the same unconfirmed duplicate again changes nothing.
        doc["observations"].append(_obs(record_id=122, action="value_freeze",
                                        confirmed=False, evidence_note=None,
                                        expected="third attempt",
                                        observed="still same result"))
        report3 = self._report_file(doc, name="report-3.json")
        out = self.base / "dup-out"
        rc3 = ap11_campaign.main(_report_argv(report3, out))
        # Fresh directory: same deduplicated result as before.
        summary3 = json.loads((out / "ap11-summary.json").read_text(
            encoding="utf-8"))
        self.assertEqual(rc3, 0)
        self.assertEqual(summary3["tables"]["case-01.ct"]["confirmed_total"], 1)
        self.assertEqual(summary3["ingestion"]["observations_total"], 3)
        self.assertEqual(summary3["ingestion"]["observations_accepted"], 1)
        self.assertEqual(summary3["ingestion"]["duplicates_removed"], 2,
                         "the confirmed observation keeps the "
                         "(record_id, action) key for both duplicates")

    def test_report_foreign_record_id_is_rejected(self):
        doc = _report_doc(observations=[
            _obs(record_id=999999, action="value_freeze", confirmed=False),
        ])
        rc, summary, state, report, out = self._ingest(doc)
        self.assertEqual(rc, 1, "a record id outside the manifest must be "
                                "rejected")
        self.assertIsNone(summary)
        self.assertFalse((out / "ap11-summary.json").exists(),
                         "a rejected report must not create evidence")
        self.assertFalse((out / "ap11-progress.json").exists())

    def test_report_confirmed_without_evidence_note_is_rejected(self):
        doc = _report_doc(observations=[
            _obs(record_id=122, action="value_freeze", confirmed=True,
                 evidence_note="   "),
        ])
        rc, summary, _, report, out = self._ingest(doc)
        self.assertEqual(rc, 1, "confirmed=true requires a non-empty "
                                "evidence_note")
        self.assertFalse((out / "ap11-summary.json").exists())
        # null evidence note is rejected the same way.
        doc = _report_doc(observations=[
            _obs(record_id=122, action="value_freeze", confirmed=True,
                 evidence_note=None),
        ])
        rc, _, _, _, _ = self._ingest(doc, out_name="ingest-null")
        self.assertEqual(rc, 1)

    def test_report_confirmed_without_game_build_id_is_rejected(self):
        doc = _report_doc(game_build_id=None, observations=[
            _obs(record_id=122, action="value_freeze", confirmed=True,
                 evidence_note="effect observed but no build id"),
        ])
        rc, _, _, _, out = self._ingest(doc)
        self.assertEqual(rc, 1, "confirmed=true requires a non-empty "
                                "game_build_id")
        self.assertFalse((out / "ap11-summary.json").exists())
        # An empty-string build id is rejected just like null.
        doc = _report_doc(game_build_id="", observations=[
            _obs(record_id=122, action="value_freeze", confirmed=True,
                 evidence_note="effect observed"),
        ])
        rc, _, _, _, _ = self._ingest(doc, out_name="ingest-empty-build")
        self.assertEqual(rc, 1)

    def test_report_empty_report_is_valid(self):
        doc = _report_doc(observations=[])
        rc, summary, state, _, _ = self._ingest(doc)
        self.assertEqual(rc, 0)
        self.assertEqual(summary["ingestion"]["observations_total"], 0)
        self.assertEqual(summary["ingestion"]["observations_accepted"], 0)
        self.assertEqual(summary["tables"]["case-01.ct"]["report_ingested"], True)
        self.assertEqual(summary["tables"]["case-01.ct"]["confirmed_total"], 0)
        self.assertEqual(summary["overall"]["confirmed_actions"], 0)
        self.assertEqual(state["tables"]["case-01.ct"]["observations"], [])

    def test_report_schema_mismatch_is_rejected(self):
        doc = _report_doc(schema="ap11-report/v2")
        rc, _, _, _, out = self._ingest(doc)
        self.assertEqual(rc, 1)
        self.assertFalse((out / "ap11-summary.json").exists())

    def test_report_unknown_table_is_rejected(self):
        doc = _report_doc(table="Not A Campaign Table")
        rc, _, _, _, out = self._ingest(doc)
        self.assertEqual(rc, 1)
        self.assertFalse((out / "ap11-summary.json").exists())

    def test_report_table_matches_by_ct_path_too(self):
        doc = _report_doc(table="case-01.ct", observations=[
            _obs(record_id=121, action="persistent_script", confirmed=False),
        ])
        rc, summary, state, _, _ = self._ingest(doc)
        self.assertEqual(rc, 0, "ct_path must be an accepted table match")
        self.assertEqual(summary["ingestion"]["table"], "case-01.ct")
        self.assertIn("case-01.ct", state["tables"])

    def test_report_action_category_mismatch_is_rejected(self):
        # Record 122 is value_freeze in the manifest; a persistent_script
        # observation for it contradicts the static classification.
        doc = _report_doc(observations=[
            _obs(record_id=122, action="persistent_script", confirmed=False),
        ])
        rc, _, _, _, out = self._ingest(doc)
        self.assertEqual(rc, 1, "action must match the record's static "
                                "category from the manifest")
        self.assertFalse((out / "ap11-summary.json").exists())
        # And a category the record does not carry at all is rejected too.
        doc = _report_doc(observations=[
            _obs(record_id=121, action="one_shot", confirmed=False),
        ])
        rc, _, _, _, _ = self._ingest(doc, out_name="ingest-wrong-cat")
        self.assertEqual(rc, 1)

    def test_report_missing_process_name_is_rejected(self):
        doc = _report_doc(process_name="")
        rc, _, _, _, out = self._ingest(doc)
        self.assertEqual(rc, 1)
        self.assertFalse((out / "ap11-summary.json").exists())
        # A non-positive pid is rejected as well.
        doc = _report_doc(process_pid=0)
        rc, _, _, _, _ = self._ingest(doc, out_name="ingest-bad-pid")
        self.assertEqual(rc, 1)

    def test_report_new_report_replaces_previous_for_table(self):
        first = _report_doc(observations=[
            _obs(record_id=121, action="persistent_script", confirmed=True,
                 evidence_note="first run evidence"),
            _obs(record_id=122, action="value_freeze", confirmed=True,
                 evidence_note="first run freeze evidence"),
        ])
        rc, summary, _, report, out = self._ingest(first)
        self.assertEqual(rc, 0)
        self.assertEqual(summary["tables"]["case-01.ct"]["confirmed_total"], 2)
        second = _report_doc(observations=[
            _obs(record_id=121, action="persistent_script", confirmed=True,
                 evidence_note="second run evidence"),
        ])
        report2 = self._report_file(second, name="report-2.json")
        rc2 = ap11_campaign.main(_report_argv(report2, out))
        self.assertEqual(rc2, 0)
        summary2 = json.loads((out / "ap11-summary.json").read_text(
            encoding="utf-8"))
        self.assertEqual(summary2["ingestion"]["replaced_previous"], True)
        self.assertEqual(summary2["tables"]["case-01.ct"]["confirmed_total"], 1,
                         "a new report file for the same table must "
                         "replace the previous observations, not merge")
        state2 = json.loads((out / "ap11-progress.json").read_text(
            encoding="utf-8"))
        self.assertEqual(len(state2["tables"]["case-01.ct"]["observations"]), 1)

    def test_report_state_from_other_campaign_is_rejected(self):
        doc = _report_doc(observations=[
            _obs(record_id=121, action="persistent_script", confirmed=False),
        ])
        rc, _, _, report, out = self._ingest(doc)
        self.assertEqual(rc, 0)
        state = json.loads((out / "ap11-progress.json").read_text(
            encoding="utf-8"))
        state["campaign_sha256"] = "0" * 64
        _write_json(out / "ap11-progress.json", state)
        rc2 = ap11_campaign.main(_report_argv(report, out))
        self.assertEqual(rc2, 1, "a progress state from a different "
                                 "campaign manifest must be rejected")

    def test_report_refuses_to_write_into_input_directories(self):
        doc = _report_doc(observations=[])
        report = self._report_file(doc, subdir=".")
        rc = ap11_campaign.main(_report_argv(report, self.base))
        self.assertEqual(rc, 3, "writing into the directory containing the "
                                "report file must be refused")
        self.assertFalse((self.base / "ap11-summary.json").exists())
