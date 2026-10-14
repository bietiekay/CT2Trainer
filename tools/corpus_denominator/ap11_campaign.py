#!/usr/bin/env python3
"""AP-11 lane tool: deterministic game-campaign plan and report ingestion.

Read-only against the committed ``gap_inventory`` artifacts and the
read-only ``TableReferences`` corpus (CT bytes are hashed and tokenized
for process-name candidates only; nothing is executed or modified).

Two subcommands:

  manifest (default)
    Writes ``ap11-campaign.json`` into ``--output``: one entry per pinned
    start table (gap-report order) with name, ct_path, ct_sha256,
    architecture, process_candidates (owned process_detect over the CT
    bytes), expected_actions, category_counts, the fixed priority_order
    (value_freeze, string_write, one_shot, persistent_script,
    custom_value) and the per-record category map that lets ``report``
    validate observations without the gap report.

  report --report <file> --campaign <manifest> --output <dir>
    Validates one user-supplied ``ap11-report/v1`` document against the
    campaign manifest, merges it into the cumulative progress state
    ``ap11-progress.json`` inside ``--output`` (latest report per table
    wins; re-ingesting the same report file is a byte-identical no-op)
    and writes ``ap11-summary.json``: confirmed actions per
    table/category and total progress versus the 5967-action
    denominator.

Validation contract (report v1):
  * schema must be ``ap11-report/v1``
  * table must match a manifest table by name or ct_path
  * process_name non-empty string, process_pid positive integer
  * game_build_id: non-empty string or null
  * observations only reference manifest records of the matched table
  * action must be one of the five categories and match the record's
    static category
  * expected/observed non-empty strings; confirmed a boolean
  * confirmed=true additionally requires a non-empty evidence_note and a
    non-empty game_build_id
  * duplicates on (record_id, action) are idempotent: a confirmed
    observation wins over an unconfirmed one, otherwise the first one
    wins

Deterministic: same inputs + same run-id => byte-identical artifacts
(sorted JSON keys, 1-space indent, no wall-clock timestamps;
``generated`` is the documented run stamp ``"run <run-id>"``).

Exit codes: 0 ok, 1 input error (missing/invalid inputs, failed report
validation, progress state from a different campaign), 2 consistency
failure (stale or damaged campaign artifacts), 3 write refused (never
into a directory containing an input artifact or the read-only corpus).

Usage:
  python tools/corpus_denominator/ap11_campaign.py [manifest] \
      [--gap-report <path>] [--inventory <path>] \
      [--feature-coverage <path>] [--corpus-root <dir>] \
      --output <out-dir> [--run-id <id>] [--list]
  python tools/corpus_denominator/ap11_campaign.py report \
      --report <file> [--campaign <manifest>] --output <dir> \
      [--run-id <id>]
"""
import argparse
import hashlib
import json
import os
import sys
from collections import Counter

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(_PKG_DIR))

try:
    from ct2trainer.native import process_detect
except ImportError:  # tool run directly without PYTHONPATH pointing at src
    sys.path.insert(0, os.path.join(REPO_ROOT, "src"))
    from ct2trainer.native import process_detect

CAMPAIGN_SCHEMA = "ap11-campaign/v1"
REPORT_SCHEMA = "ap11-report/v1"
PROGRESS_SCHEMA = "ap11-progress/v1"
SUMMARY_SCHEMA = "ap11-summary/v1"
DEFAULT_RUN_ID = "repo-reproducible"

DEFAULT_GAP_REPORT = os.path.join(REPO_ROOT, "gap_inventory", "gap-report.json")
DEFAULT_INVENTORY = os.path.join(REPO_ROOT, "gap_inventory", "inventory.json")
DEFAULT_FEATURE_COVERAGE = os.path.join(REPO_ROOT, "gap_inventory", "feature-coverage.json")
DEFAULT_CAMPAIGN = os.path.join(REPO_ROOT, "gap_inventory", "ap11-campaign.json")
DEFAULT_CORPUS_ROOT = os.path.join(REPO_ROOT, "TableReferences")

# Fixed per-table action category priority for the AP-11 campaign:
# cheap reversible memory work first, script lifecycles last.
CATEGORY_PRIORITY = ("value_freeze", "string_write", "one_shot",
                     "persistent_script", "custom_value")

REQUIRED_REPORT_KEYS = ("generated", "run_id", "lane", "counting_convention",
                        "gap_labels", "pinned_tables", "corpus_rest",
                        "denominator", "top_gaps_pinned")
REQUIRED_INVENTORY_KEYS = ("generated", "run_id", "tables")
REQUIRED_COVERAGE_KEYS = ("schema", "consistency")
REQUIRED_CAMPAIGN_KEYS = ("schema", "generated", "run_id", "source",
                          "convention", "denominator", "totals",
                          "consistency", "tables")


def sha256_file(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def load_json(path):
    if not os.path.isfile(path):
        raise FileNotFoundError("input artifact missing: %s" % path)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(out_dir, name, obj):
    path = os.path.join(out_dir, name)
    # newline="\n" keeps committed baselines byte-identical on every platform
    # (text-mode writes would translate to CRLF on Windows and break the
    # byte-reproducibility check).
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")
    return path


def _refused(out_dir, protected_dirs):
    out = os.path.normpath(out_dir).lower()
    for d in protected_dirs:
        base = os.path.normpath(d).lower()
        if out == base or out.startswith(base + os.sep):
            return True
    return False


def _check(name, expected, actual):
    return {"check": name, "ok": expected == actual,
            "expected": expected, "actual": actual}


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _nonempty_str(value):
    return isinstance(value, str) and value.strip() != ""


def build_tables(gap_report, corpus_root):
    """One campaign entry per pinned table, in gap-report order.

    Raises ``FileNotFoundError`` when a pinned CT is absent from
    ``corpus_root`` (input error, exit 1). Returns ``(tables,
    sha_mismatches)``; a CT whose bytes no longer match the pinned SHA is
    collected for the consistency section (exit 2), never silently used.
    """
    tables = []
    sha_mismatches = []
    for table in gap_report["pinned_tables"]:
        counts = table["counts"]
        categories = counts["categories"]
        records = {}
        for group in table["records_by_group"]:
            for rec in group["records"]:
                records[str(rec["id"])] = rec["category"]
        ct_path = os.path.join(corpus_root, *table["path"].split("/"))
        with open(ct_path, "rb") as f:
            data = f.read()
        actual_sha = hashlib.sha256(data).hexdigest()
        if actual_sha != table["sha256"]:
            sha_mismatches.append({
                "name": table["table"],
                "ct_path": table["path"],
                "expected_sha256": table["sha256"],
                "actual_sha256": actual_sha,
            })
        tables.append({
            "name": table["table"],
            "ct_path": table["path"],
            "ct_sha256": table["sha256"],
            "architecture": table["architecture"]["value"],
            "process_candidates": process_detect.find_candidates(data),
            "expected_actions": counts["expected_actions"],
            "navigation_excluded": counts.get("navigation_excluded", 0),
            "category_counts": {c: categories[c] for c in CATEGORY_PRIORITY
                                if c in categories},
            "priority_order": [c for c in CATEGORY_PRIORITY
                               if categories.get(c, 0) > 0],
            "records": records,
        })
    return tables, sha_mismatches


def build_manifest_consistency(gap_report, inventory, feature_coverage,
                               tables, sha_mismatches):
    """Cross-check the manifest against the committed AP-10 artifacts.

    Every check is a ``(name, ok, expected, actual)`` record; ``all_ok`` is
    the conjunction. A failing check means the manifest, the gap report,
    the inventory or the corpus disagree and the run must not be consumed
    as evidence (exit 2).
    """
    denom = gap_report["denominator"]
    checks = []
    add = checks.append

    add(_check("pinned_table_count", denom["unique_tables"], len(tables)))
    add(_check("expected_actions", denom["expected_actions"],
               sum(t["expected_actions"] for t in tables)))
    total_categories = Counter()
    for table in tables:
        total_categories.update(table["category_counts"])
    total_nav = sum(t["navigation_excluded"] for t in tables)
    if total_nav:
        total_categories["navigation"] = total_categories.get("navigation", 0) + total_nav
    add(_check("category_counts", dict(sorted(denom["category_counts"].items())),
               dict(sorted(total_categories.items()))))
    add(_check("confirmed_game_effect_zero", 0,
               denom["confirmed_game_effect_actions"]))

    per_table = []
    for table in tables:
        navigation = table["navigation_excluded"]
        ok = (sum(table["category_counts"].values()) == table["expected_actions"]
              and len(table["records"]) == table["expected_actions"] + navigation
              and set(table["category_counts"]) <= set(CATEGORY_PRIORITY)
              and set(table["records"].values()) <= set(CATEGORY_PRIORITY) | {"navigation"})
        per_table.append({"name": table["name"], "ok": ok})
    checks.append({"check": "per_table_counts",
                   "ok": all(row["ok"] for row in per_table),
                   "tables": per_table})

    checks.append(_check("ct_sha_integrity", [], sha_mismatches))

    inventory_shas = {t["sha256"] for t in inventory["tables"]}
    pinned_shas = {t["ct_sha256"] for t in tables}
    checks.append(_check("inventory_covers_campaign_shas",
                         sorted(pinned_shas),
                         sorted(pinned_shas & inventory_shas)))

    fc_checks = {c["check"]: c for c in feature_coverage["consistency"]["checks"]}
    fc_problems = []
    if not feature_coverage["consistency"].get("all_ok", False):
        fc_problems.append("feature_coverage consistency all_ok is false")
    expected_actions_row = fc_checks.get("expected_actions")
    if (expected_actions_row is None
            or expected_actions_row.get("actual") != denom["expected_actions"]):
        fc_problems.append(
            "feature_coverage expected_actions disagrees with the gap report")
    shas_row = fc_checks.get("pinned_shas_in_inventory")
    if shas_row is None or shas_row.get("actual") != sorted(pinned_shas):
        fc_problems.append(
            "feature_coverage pinned SHAs disagree with the campaign tables")
    checks.append(_check("feature_coverage_agrees", [], fc_problems))

    return {"all_ok": all(c["ok"] for c in checks), "checks": checks}


def build_manifest_document(gap_report, inventory, feature_coverage,
                            corpus_root, run_id, source_paths):
    """Assemble the deterministic ``ap11-campaign/v1`` document."""
    tables, sha_mismatches = build_tables(gap_report, corpus_root)
    consistency = build_manifest_consistency(
        gap_report, inventory, feature_coverage, tables, sha_mismatches)
    denom = gap_report["denominator"]
    total_categories = Counter()
    for table in tables:
        total_categories.update(table["category_counts"])
    total_nav = sum(t["navigation_excluded"] for t in tables)
    if total_nav:
        total_categories["navigation"] = total_categories.get("navigation", 0) + total_nav
    document = {
        "schema": CAMPAIGN_SCHEMA,
        "generated": "run %s" % run_id,
        "run_id": run_id,
        "lane": "AP-11 game campaign plan (read-only, static)",
        "source": dict(source_paths),
        "convention": {
            "counting": gap_report["counting_convention"],
            "priority_order": list(CATEGORY_PRIORITY),
            "priority_rule": "per-table priority_order is the fixed category "
                             "priority restricted to the table's non-zero "
                             "categories; the campaign walks value_freeze "
                             "first and script lifecycles last",
            "record_map": "records maps str(record id) to the record's "
                          "static category; report observations may only "
                          "reference these ids",
        },
        "denominator": {
            "unique_tables": denom["unique_tables"],
            "expected_actions": denom["expected_actions"],
            "category_counts": denom["category_counts"],
            "confirmed_game_effect_actions":
                denom["confirmed_game_effect_actions"],
            "goal_90_percent": denom["goal_90_percent"],
        },
        "totals": {
            "tables": len(tables),
            "expected_actions": sum(t["expected_actions"] for t in tables),
            "category_counts": dict(sorted(total_categories.items())),
        },
        "consistency": consistency,
        "tables": tables,
    }
    return document


def campaign_checks(campaign):
    """Internal consistency of a campaign manifest (report-side gate)."""
    checks = []
    denom = campaign.get("denominator", {})
    totals = campaign.get("totals", {})
    tables = campaign.get("tables", [])
    checks.append(_check("schema", CAMPAIGN_SCHEMA, campaign.get("schema")))
    checks.append(_check("pinned_table_count",
                         denom.get("unique_tables"), len(tables)))
    checks.append(_check("expected_actions", denom.get("expected_actions"),
                         totals.get("expected_actions")))
    checks.append(_check("category_counts",
                         denom.get("category_counts"),
                         totals.get("category_counts")))
    names = set()
    per_table = []
    for table in tables:
        cats = table.get("category_counts", {})
        records = table.get("records", {})
        navigation = table.get("navigation_excluded", 0)
        ok = (set(cats) <= set(CATEGORY_PRIORITY)
              and set(records.values()) <= set(CATEGORY_PRIORITY) | {"navigation"}
              and sum(cats.values()) == table.get("expected_actions")
              and len(records) == table.get("expected_actions") + navigation
              and table.get("priority_order") == [
                  c for c in CATEGORY_PRIORITY if cats.get(c, 0) > 0])
        per_table.append({"name": table.get("name"), "ok": ok})
        names.add(table.get("name"))
    checks.append({"check": "table_names_unique",
                   "ok": len(names) == len(tables),
                   "expected": len(tables), "actual": len(names)})
    checks.append({"check": "per_table_counts",
                   "ok": all(r["ok"] for r in per_table),
                   "tables": per_table})
    return {"all_ok": all(c["ok"] for c in checks), "checks": checks}


def _match_table(value, tables):
    if not _nonempty_str(value):
        return None
    for table in tables:
        if value == table["name"] or value == table["ct_path"]:
            return table
    return None


def validate_report(report, campaign):
    """Validate one ap11-report/v1 document against the campaign.

    Returns ``(errors, matched_table, deduped_observations,
    duplicates_removed)``. Deduplication key is ``(record_id, action)``:
    a confirmed observation wins over an unconfirmed duplicate,
    otherwise the first observation wins. Invalid observations are
    reported and excluded from the deduplicated list.
    """
    errors = []
    if not isinstance(report, dict):
        return ["report root must be a JSON object"], None, [], 0
    if report.get("schema") != REPORT_SCHEMA:
        errors.append("schema must be %r" % REPORT_SCHEMA)
    matched = _match_table(report.get("table"), campaign["tables"])
    if "table" not in report or report.get("table") is None:
        errors.append("table is required")
    elif matched is None:
        errors.append("table %r is not a campaign table" % report.get("table"))
    if not _nonempty_str(report.get("process_name")):
        errors.append("process_name must be a non-empty string")
    process_pid = report.get("process_pid")
    if not _is_int(process_pid) or process_pid <= 0:
        errors.append("process_pid must be a positive integer")
    game_build_id = report.get("game_build_id")
    if game_build_id is not None and not _nonempty_str(game_build_id):
        errors.append("game_build_id must be null or a non-empty string")
    observations = report.get("observations")
    if not isinstance(observations, list):
        errors.append("observations must be a list")
        return errors, matched, [], 0

    records = matched["records"] if matched is not None else {}
    deduped = []
    seen = {}
    duplicates_removed = 0
    for index, obs in enumerate(observations):
        where = "observations[%d]" % index
        if not isinstance(obs, dict):
            errors.append(where + " must be an object")
            continue
        record_id = obs.get("record_id")
        if not _is_int(record_id):
            errors.append(where + ".record_id must be an integer")
            continue
        if records and str(record_id) not in records:
            errors.append(
                "%s.record_id %d is not a record of %s"
                % (where, record_id, matched["name"] if matched else "table"))
            continue
        action = obs.get("action")
        if action not in CATEGORY_PRIORITY:
            errors.append(where + ".action must be one of "
                           + ", ".join(CATEGORY_PRIORITY))
            continue
        if records and records[str(record_id)] != action:
            errors.append(
                "%s: action %r does not match record %d category %r"
                % (where, action, record_id, records[str(record_id)]))
            continue
        if not _nonempty_str(obs.get("expected")):
            errors.append(where + ".expected must be a non-empty string")
        if not _nonempty_str(obs.get("observed")):
            errors.append(where + ".observed must be a non-empty string")
        confirmed = obs.get("confirmed")
        if not isinstance(confirmed, bool):
            errors.append(where + ".confirmed must be a boolean")
            continue
        evidence_note = obs.get("evidence_note")
        if evidence_note is not None and not isinstance(evidence_note, str):
            errors.append(where + ".evidence_note must be null or a string")
            continue
        if confirmed:
            if not _nonempty_str(evidence_note):
                errors.append(where
                              + ": confirmed=true requires a non-empty "
                                "evidence_note")
            if not _nonempty_str(game_build_id):
                errors.append(where
                              + ": confirmed=true requires a non-empty "
                                "game_build_id")
        key = (record_id, action)
        if key in seen:
            duplicates_removed += 1
            if confirmed and not deduped[seen[key]]["confirmed"]:
                deduped[seen[key]] = obs
        else:
            seen[key] = len(deduped)
            deduped.append(obs)
    return errors, matched, deduped, duplicates_removed


def build_summary(campaign, state, ingested_table, deduped,
                  duplicates_removed, replaced, report_sha, args):
    """Summary over the merged progress state, covering every campaign
    table so the per-table/per-category confirmed counts stay complete
    against the 5967-action denominator."""
    tables = {}
    for table in campaign["tables"]:
        entry = state["tables"].get(table["name"])
        confirmed = Counter()
        if entry is not None:
            for obs in entry["observations"]:
                if obs["confirmed"]:
                    confirmed[obs["action"]] += 1
        tables[table["name"]] = {
            "ct_path": table["ct_path"],
            "expected_actions": table["expected_actions"],
            "categories": table["category_counts"],
            "confirmed_by_category": dict(sorted(confirmed.items())),
            "confirmed_total": sum(confirmed.values()),
            "report_ingested": entry is not None,
            "process_name": entry["process_name"] if entry else None,
            "process_pid": entry["process_pid"] if entry else None,
            "game_build_id": entry["game_build_id"] if entry else None,
        }
    expected_total = campaign["totals"]["expected_actions"]
    confirmed_total = sum(t["confirmed_total"] for t in tables.values())
    percent = (round(100.0 * confirmed_total / expected_total, 2)
               if expected_total else 0.0)
    return {
        "schema": SUMMARY_SCHEMA,
        "generated": "run %s" % args.run_id,
        "run_id": args.run_id,
        "lane": "AP-11 game campaign progress summary (read-only inputs)",
        "source": {
            "campaign": os.path.abspath(args.campaign),
            "campaign_sha256": state["campaign_sha256"],
            "report": os.path.abspath(args.report),
            "report_sha256": report_sha,
        },
        "campaign_totals": {
            "tables": campaign["totals"]["tables"],
            "expected_actions": expected_total,
            "category_counts": campaign["totals"]["category_counts"],
        },
        "ingestion": {
            "table": ingested_table["name"],
            "observations_total": len(deduped) + duplicates_removed,
            "observations_accepted": len(deduped),
            "duplicates_removed": duplicates_removed,
            "replaced_previous": replaced,
        },
        "tables": tables,
        "overall": {
            "expected_actions": expected_total,
            "confirmed_actions": confirmed_total,
            "confirmed_percent": percent,
            "remaining_actions": expected_total - confirmed_total,
            "goal_percent": 90.0,
            "goal_reached": (expected_total > 0
                             and confirmed_total / expected_total >= 0.90),
            "confirmed_game_effect_actions": confirmed_total,
        },
    }


def run_report(args):
    try:
        campaign = load_json(args.campaign)
        report = load_json(args.report)
    except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
        print("input error:", e)
        return 1
    missing = [k for k in REQUIRED_CAMPAIGN_KEYS if k not in campaign]
    if missing:
        print("campaign manifest missing keys:", missing)
        return 1

    out_dir = os.path.abspath(args.output)
    protected = [os.path.dirname(os.path.abspath(args.report)),
                 os.path.dirname(os.path.abspath(args.campaign))]
    if _refused(out_dir, protected):
        print("refusing to write into a directory containing the input "
              "artifacts:", args.output)
        return 3

    consistency = campaign_checks(campaign)
    if not consistency["all_ok"]:
        for row in [c for c in consistency["checks"] if not c["ok"]]:
            print("CAMPAIGN CONSISTENCY FAIL:", row["check"])
            if "expected" in row:
                print("  expected:", row["expected"])
            if "actual" in row:
                print("  actual:  ", row["actual"])
            if "tables" in row:
                for t in row["tables"]:
                    if not t["ok"]:
                        print("  table:", t["name"])
        return 2

    errors, matched, deduped, duplicates_removed = validate_report(
        report, campaign)
    if errors:
        for e in errors:
            print("report validation error:", e)
        return 1

    campaign_sha = sha256_file(args.campaign)
    report_sha = sha256_file(args.report)
    state_path = os.path.join(out_dir, "ap11-progress.json")
    state = {"schema": PROGRESS_SCHEMA, "campaign_sha256": campaign_sha,
             "tables": {}}
    if os.path.isfile(state_path):
        try:
            state = load_json(state_path)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            print("input error: progress state is unreadable")
            return 1
        if state.get("schema") != PROGRESS_SCHEMA:
            print("input error: progress state schema mismatch")
            return 1
        if state.get("campaign_sha256") != campaign_sha:
            print("input error: progress state belongs to a different "
                  "campaign manifest")
            return 1
        if not isinstance(state.get("tables"), dict):
            print("input error: progress state has no table map")
            return 1

    previous = state["tables"].get(matched["name"])
    replaced = (previous is not None
                and previous.get("report_sha256") != report_sha)
    state["tables"][matched["name"]] = {
        "report_sha256": report_sha,
        "process_name": report["process_name"],
        "process_pid": report["process_pid"],
        "game_build_id": report.get("game_build_id"),
        "observations": deduped,
    }

    summary = build_summary(campaign, state, matched, deduped,
                            duplicates_removed, replaced, report_sha, args)
    os.makedirs(out_dir, exist_ok=True)
    _write_json(out_dir, "ap11-progress.json", state)
    out = _write_json(out_dir, "ap11-summary.json", summary)
    print("wrote", out, os.path.getsize(out), "bytes")
    row = summary["tables"][matched["name"]]
    print("table %s: %d confirmed of %d expected actions"
          % (matched["name"], row["confirmed_total"],
             matched["expected_actions"]))
    overall = summary["overall"]
    print("overall: %d/%d confirmed actions (%.2f%%, goal 90%%)"
          % (overall["confirmed_actions"], overall["expected_actions"],
             overall["confirmed_percent"]))
    return 0


def _list_tables(tables):
    for table in tables:
        print("%-46s %-58s %-7s candidates=%-24s expected=%-5d priority=%s"
              % (table["name"], table["ct_path"], table["architecture"],
                 ",".join(table["process_candidates"]) or "(none)",
                 table["expected_actions"],
                 "/".join(table["priority_order"])))


def run_manifest(args):
    try:
        gap_report = load_json(args.gap_report)
        inventory = load_json(args.inventory)
        feature_coverage = load_json(args.feature_coverage)
    except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
        print("input error:", e)
        return 1
    missing = [k for k in REQUIRED_REPORT_KEYS if k not in gap_report]
    if missing:
        print("gap report missing keys:", missing)
        return 1
    missing = [k for k in REQUIRED_INVENTORY_KEYS if k not in inventory]
    if missing:
        print("inventory missing keys:", missing)
        return 1
    missing = [k for k in REQUIRED_COVERAGE_KEYS if k not in feature_coverage]
    if missing:
        print("feature coverage missing keys:", missing)
        return 1

    corpus_root = os.path.abspath(args.corpus_root)
    out_dir = os.path.abspath(args.output) if args.output else None
    if out_dir is not None:
        protected = [os.path.dirname(os.path.abspath(args.gap_report)),
                     os.path.dirname(os.path.abspath(args.inventory)),
                     os.path.dirname(os.path.abspath(args.feature_coverage)),
                     corpus_root]
        if _refused(out_dir, protected):
            print("refusing to write into a directory containing the input "
                  "artifacts or the read-only corpus:", args.output)
            return 3

    try:
        tables, sha_mismatches = build_tables(gap_report, corpus_root)
    except FileNotFoundError as e:
        print("input error:", e)
        return 1

    if args.list:
        _list_tables(tables)
        return 0

    if out_dir is None:
        print("an output directory is required unless --list is used")
        return 2

    document = build_manifest_document(
        gap_report, inventory, feature_coverage, corpus_root, args.run_id,
        {
            "gap_report": os.path.abspath(args.gap_report),
            "gap_report_sha256": sha256_file(args.gap_report),
            "inventory": os.path.abspath(args.inventory),
            "inventory_sha256": sha256_file(args.inventory),
            "feature_coverage": os.path.abspath(args.feature_coverage),
            "feature_coverage_sha256": sha256_file(args.feature_coverage),
            "corpus_root": corpus_root,
        })
    os.makedirs(out_dir, exist_ok=True)
    out = _write_json(out_dir, "ap11-campaign.json", document)
    print("wrote", out, os.path.getsize(out), "bytes")
    print("tables:", document["totals"]["tables"],
          "expected actions:", document["totals"]["expected_actions"])
    for row in [c for c in document["consistency"]["checks"]
                if not c["ok"]]:
        print("CONSISTENCY FAIL:", row["check"])
        if "expected" in row:
            print("  expected:", row["expected"])
        if "actual" in row:
            print("  actual:  ", row["actual"])
        if "tables" in row:
            for t in row["tables"]:
                if not t["ok"]:
                    print("  table:", t["name"])
    print("consistency all_ok:", document["consistency"]["all_ok"])
    return 0 if document["consistency"]["all_ok"] else 2


def _add_manifest_arguments(parser):
    parser.add_argument("--gap-report", default=DEFAULT_GAP_REPORT,
                        help="path to gap-report.json (default: repo "
                             "gap_inventory/gap-report.json)")
    parser.add_argument("--inventory", default=DEFAULT_INVENTORY,
                        help="path to inventory.json (default: repo "
                             "gap_inventory/inventory.json)")
    parser.add_argument("--feature-coverage", default=DEFAULT_FEATURE_COVERAGE,
                        help="path to feature-coverage.json (default: repo "
                             "gap_inventory/feature-coverage.json)")
    parser.add_argument("--corpus-root", default=DEFAULT_CORPUS_ROOT,
                        help="read-only CT corpus root (default: repo "
                             "TableReferences)")
    parser.add_argument("--output", default=None,
                        help="directory receiving ap11-campaign.json "
                             "(required unless --list)")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID,
                        help="deterministic run identifier carried in the "
                             "'generated' and 'run_id' fields")
    parser.add_argument("--list", action="store_true",
                        help="print the per-table plan and exit")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="ap11_campaign",
        description="Deterministic AP-11 game-campaign plan and report "
                    "ingestion from the committed gap artifacts "
                    "(read-only, static, stdlib only).")
    subparsers = parser.add_subparsers(dest="command")
    manifest_parser = subparsers.add_parser(
        "manifest", help="write ap11-campaign.json (default subcommand)")
    _add_manifest_arguments(manifest_parser)
    report_parser = subparsers.add_parser(
        "report", help="validate and ingest one ap11-report/v1 file")
    report_parser.add_argument("--report", required=True,
                               help="path to the report JSON "
                                    "(ap11-report/v1)")
    report_parser.add_argument("--campaign", default=DEFAULT_CAMPAIGN,
                               help="path to ap11-campaign.json (default: "
                                    "repo gap_inventory/ap11-campaign.json)")
    report_parser.add_argument("--output", required=True,
                               help="directory receiving ap11-progress.json "
                                    "and ap11-summary.json")
    report_parser.add_argument("--run-id", default=DEFAULT_RUN_ID,
                               help="deterministic run identifier carried "
                                    "in the 'generated' and 'run_id' fields")
    _add_manifest_arguments(parser)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.command == "report":
        return run_report(args)
    return run_manifest(args)


if __name__ == "__main__":
    sys.exit(main())
