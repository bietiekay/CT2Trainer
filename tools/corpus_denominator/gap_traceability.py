#!/usr/bin/env python3
"""AP-10 lane tool: deterministic record-level traceability for the gap report.

Read-only against the committed ``gap_inventory`` artifacts (this tool never
reads the corpus directory at all). It re-derives one trace row per pinned
table record from ``gap-report.json`` and produces, in ``--output``:

  traceability.json
    trace_entries      one row per pinned-table record (gap-report order) with
                       expected-action flag, providers, lifetime, architecture,
                       target build, semantics and the open APIs (gap ->
                       requirement) needed to satisfy it
    gap_index          reverse index: gap id -> affected records per table
    requirement_index  rollup per requirement id (N-xx / AP-xx / ...): which
                       gaps and how many expected actions it blocks
    consistency        cross-checks that the trace reproduces the gap report's
                       denominator, per-table counts, the inventory totals and
                       the six byte-pinned reference tables

Deterministic: same inputs + same run-id => byte-identical artifact (sorted
JSON keys, 1-space indent, no wall-clock timestamps; ``generated`` is the
documented run stamp ``"run <run-id>"``).

Exit codes: 0 ok + all consistency checks passed, 1 input error,
2 consistency failure (stale or damaged artifacts), 3 write refused
(never into the directory containing the input artifacts).

Usage:
  python tools/corpus_denominator/gap_traceability.py \
      [--gap-report <path>] [--inventory <path>] \
      --output <out-dir> [--run-id <id>]
"""
import argparse
import hashlib
import json
import os
import sys
from collections import Counter

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCHEMA_NAME = "corpus-traceability/v1"
DEFAULT_RUN_ID = "repo-reproducible"

_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(_PKG_DIR))
DEFAULT_GAP_REPORT = os.path.join(REPO_ROOT, "gap_inventory", "gap-report.json")
DEFAULT_INVENTORY = os.path.join(REPO_ROOT, "gap_inventory", "inventory.json")

REQUIRED_REPORT_KEYS = (
    "generated", "run_id", "lane", "counting_convention", "gap_labels",
    "pinned_tables", "corpus_rest", "denominator", "top_gaps_pinned",
)
REQUIRED_INVENTORY_KEYS = (
    "generated", "run_id", "tables", "totals",
    "reference_verification", "reference_verification_all_ok",
)


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
    # (text-mode writes would translate to CRLF on Windows).
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


def _open_apis(gaps, gap_labels):
    out = []
    for gap in gaps:
        entry = gap_labels.get(gap)
        if entry is None:
            out.append({"gap": gap, "label": None, "requirement": None,
                        "unmapped": True})
        else:
            out.append({"gap": gap, "label": entry["label"],
                        "requirement": entry["requirement"],
                        "unmapped": False})
    return out


def build_trace_entries(gap_report):
    """One trace row per pinned-table record, in gap-report document order.

    The gap report already carries the per-record static classification
    (type, category, status, gaps, providers, lifetime, architecture,
    target_build, semantics, async, address_kind); this tool only adds the
    expected-action flag, the stable trace id and the open-API mapping.
    """
    labels = gap_report["gap_labels"]
    entries = []
    index = 0
    for table in gap_report["pinned_tables"]:
        for group in table["records_by_group"]:
            for rec in group["records"]:
                entry = {
                    "entry_index": index,
                    "trace_id": "%s#%s" % (table["path"], rec["id"]),
                    "table": table["table"],
                    "table_path": table["path"],
                    "table_sha256": table["sha256"],
                    "group_breadcrumb": group["group"],
                    "record_id": rec["id"],
                    "record_name": rec["name"],
                    "type": rec["type"],
                    "category": rec["category"],
                    "status": rec["status"],
                    "gaps": list(rec["gaps"]),
                    "providers": list(rec.get("providers", [])),
                    "lifetime": rec.get("lifetime"),
                    "architecture": rec.get("architecture"),
                    "target_build": rec.get("target_build"),
                    "semantics": rec.get("semantics"),
                    "parent": rec.get("parent"),
                    "depth": rec.get("depth"),
                    "async": rec.get("async"),
                    "address_kind": rec.get("address_kind"),
                    "expected_action": rec["category"] != "navigation",
                    "open_apis": _open_apis(rec["gaps"], labels),
                }
                entries.append(entry)
                index += 1
    return entries


def build_gap_index(entries, gap_report):
    """Reverse index: every gap id -> the concrete records that produce it.

    Tables keep the gap report's order; record ids keep document order.
    Gap ids present in the trace but absent from ``gap_labels`` are listed
    under ``unmapped_gaps`` instead of silently dropped.
    """
    labels = gap_report["gap_labels"]
    per_gap = {}
    for entry in entries:
        for gap in entry["gaps"]:
            slot = per_gap.setdefault(
                gap, {"tables": [], "affected_records": 0})
            for row in slot["tables"]:
                if row["table"] == entry["table"]:
                    row["records"].append(entry["record_id"])
                    break
            else:
                slot["tables"].append({
                    "table": entry["table"],
                    "path": entry["table_path"],
                    "records": [entry["record_id"]],
                })
            slot["affected_records"] += 1

    gaps = {}
    for gap in sorted(per_gap):
        meta = labels.get(gap)
        gaps[gap] = {
            "label": meta["label"] if meta else None,
            "requirement": meta["requirement"] if meta else None,
            "affected_records": per_gap[gap]["affected_records"],
            "tables": per_gap[gap]["tables"],
        }
    unmapped = sorted(set(per_gap) - set(labels))
    return {"gaps": gaps, "unmapped_gaps": unmapped,
            "gap_counts": {gap: per_gap[gap]["affected_records"]
                           for gap in sorted(per_gap)}}


def build_requirement_index(entries, gap_report):
    """Roll trace rows up by requirement id.

    Requirement strings like ``"N-07 / N-19"`` are split on ``" / "``; a
    requirement entry counts the distinct expected actions that carry at
    least one gap mapped to it, plus per-gap and per-status counts.
    """
    labels = gap_report["gap_labels"]
    gap_to_reqs = {}
    for gap, meta in labels.items():
        reqs = [part.strip() for part in meta["requirement"].split("/")]
        gap_to_reqs[gap] = sorted(set(reqs))

    req = {}
    for entry in entries:
        if not entry["expected_action"]:
            continue
        for req_id in sorted({r for gap in entry["gaps"]
                              for r in gap_to_reqs.get(gap, [])}):
            slot = req.setdefault(req_id, {"gaps": Counter(),
                                           "records": set(),
                                           "status_counts": Counter()})
            slot["records"].add(entry["entry_index"])
            slot["status_counts"][entry["status"]] += 1
            for gap in entry["gaps"]:
                if req_id in gap_to_reqs.get(gap, []):
                    slot["gaps"][gap] += 1

    out = {}
    for req_id in sorted(req):
        slot = req[req_id]
        out[req_id] = {
            "gaps": dict(sorted(slot["gaps"].items())),
            "affected_expected_actions": len(slot["records"]),
            "status_counts": dict(sorted(slot["status_counts"].items())),
        }
    return out


def build_consistency(entries, gap_report, inventory):
    """Cross-check that the trace reproduces the committed artifacts.

    Every check is a (name, ok, expected, actual) record; ``all_ok`` is the
    conjunction. A failing check means the trace tool, the gap report or the
    inventory disagree and the run must not be consumed as evidence.
    """
    denom = gap_report["denominator"]
    labels = gap_report["gap_labels"]
    tables = gap_report["pinned_tables"]
    checks = []

    def add(name, expected, actual):
        checks.append({"check": name, "ok": expected == actual,
                       "expected": expected, "actual": actual})
        return expected == actual

    status = Counter(e["status"] for e in entries)
    category = Counter(e["category"] for e in entries)
    rtype = Counter(e["type"] for e in entries)
    gaps_all = Counter()
    for e in entries:
        for g in e["gaps"]:
            gaps_all[g] += 1

    add("pinned_table_count", denom["unique_tables"], len(tables))
    add("records_total", denom["records_total"], len(entries))
    add("expected_actions", denom["expected_actions"],
        sum(1 for e in entries if e["expected_action"]))
    add("navigation_excluded", denom["navigation_excluded"],
        sum(1 for e in entries if not e["expected_action"]))
    add("status_counts", denom["status_counts"], dict(sorted(status.items())))
    add("category_counts", denom["category_counts"], dict(sorted(category.items())))
    add("record_types", denom["record_types"], dict(sorted(rtype.items())))

    report_gap_total = Counter()
    for t in tables:
        for g, n in t["counts"]["gap_counts"].items():
            report_gap_total[g] += n
    add("gap_counts_total", dict(sorted(report_gap_total.items())),
        dict(sorted(gaps_all.items())))

    per_table = []
    for t in tables:
        rows = [e for e in entries if e["table_path"] == t["path"]]
        gap_rows = Counter()
        for e in rows:
            for g in e["gaps"]:
                gap_rows[g] += 1
        per_table.append({
            "table": t["table"],
            "records": len(rows) == t["counts"]["records"],
            "expected_actions": (
                sum(1 for e in rows if e["expected_action"])
                == t["counts"]["expected_actions"]),
            "status_counts": dict(sorted(Counter(
                e["status"] for e in rows).items()))
            == t["counts"]["status_counts"],
            "category_counts": dict(sorted(Counter(
                e["category"] for e in rows).items()))
            == t["counts"]["categories"],
            "gap_counts": dict(sorted(gap_rows.items()))
            == t["counts"]["gap_counts"],
        })
    per_table_ok = all(
        all(row[key] for key in ("records", "expected_actions",
                                 "status_counts", "category_counts",
                                 "gap_counts"))
        for row in per_table)
    checks.append({"check": "per_table_counts", "ok": per_table_ok,
                   "tables": per_table})
    add("group_toggle_actions", denom["group_toggle_actions"],
        sum(t["counts"]["group_toggle_actions"] for t in tables))
    add("confirmed_game_effect_actions",
        denom["confirmed_game_effect_actions"], 0)
    add("goal_90_percent", "NOT REACHED", denom["goal_90_percent"])

    rest = gap_report["corpus_rest"]
    pinned_records = sum(t["counts"]["records"] for t in tables)
    pinned_expected = sum(t["counts"]["expected_actions"] for t in tables)
    inv = inventory["totals"]
    add("inventory_records_total", inv["records"],
        pinned_records + rest["records"])
    add("inventory_expected_actions_total", inv["expected_actions"],
        pinned_expected + rest["expected_actions"])
    pinned_shas = {t["sha256"] for t in tables}
    inv_shas = {t["sha256"] for t in inventory["tables"]}
    add("inventory_covers_pinned_shas", sorted(pinned_shas),
        sorted(pinned_shas & inv_shas))

    refs = inventory["reference_verification"]
    ref_ok = inventory["reference_verification_all_ok"] and \
        all(v["hash_match"] and v["entry_match"] for v in refs.values())
    add("reference_pins_all_ok", True, bool(ref_ok))

    add("gap_labels_cover_trace_gaps", sorted(set(gaps_all)),
        sorted(set(gaps_all) & set(labels)))

    return {"all_ok": all(c["ok"] for c in checks), "checks": checks}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="gap_traceability",
        description="Deterministic record-level traceability for the "
                    "committed AP-10 gap report (read-only, stdlib only).")
    parser.add_argument("--gap-report", default=DEFAULT_GAP_REPORT,
                        help="path to gap-report.json (default: "
                             "repo gap_inventory/gap-report.json)")
    parser.add_argument("--inventory", default=DEFAULT_INVENTORY,
                        help="path to inventory.json (default: "
                             "repo gap_inventory/inventory.json)")
    parser.add_argument("--output", required=True,
                        help="directory receiving traceability.json")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID,
                        help="deterministic run identifier carried in the "
                             "'generated' and 'run_id' fields")
    return parser.parse_args(argv)


def run(args):
    try:
        gap_report = load_json(args.gap_report)
        inventory = load_json(args.inventory)
    except (FileNotFoundError, json.JSONDecodeError) as e:
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

    out_dir = os.path.abspath(args.output)
    protected = [os.path.dirname(os.path.abspath(args.gap_report)),
                 os.path.dirname(os.path.abspath(args.inventory))]
    if _refused(out_dir, protected):
        print("refusing to write into the directory containing the "
              "input artifacts:", args.output)
        return 3

    entries = build_trace_entries(gap_report)
    gap_index = build_gap_index(entries, gap_report)
    requirement_index = build_requirement_index(entries, gap_report)
    consistency = build_consistency(entries, gap_report, inventory)

    expected = sum(1 for e in entries if e["expected_action"])
    document = {
        "schema": SCHEMA_NAME,
        "generated": "run %s" % args.run_id,
        "run_id": args.run_id,
        "lane": "AP-10 record-level traceability (read-only, static)",
        "source": {
            "gap_report": os.path.abspath(args.gap_report),
            "gap_report_sha256": sha256_file(args.gap_report),
            "inventory": os.path.abspath(args.inventory),
            "inventory_sha256": sha256_file(args.inventory),
        },
        "counting_convention": gap_report["counting_convention"],
        "totals": {
            "trace_entries": len(entries),
            "expected_actions": expected,
            "navigation_excluded": len(entries) - expected,
            "unique_gaps": len(gap_index["gap_counts"]),
            "gap_occurrences": sum(gap_index["gap_counts"].values()),
            "requirements": len(requirement_index),
        },
        "gap_index": gap_index,
        "requirement_index": requirement_index,
        "consistency": consistency,
        "trace_entries": entries,
    }

    os.makedirs(out_dir, exist_ok=True)
    out = _write_json(out_dir, "traceability.json", document)
    print("wrote", out, os.path.getsize(out), "bytes")
    print("trace entries:", len(entries), "expected actions:", expected,
          "unique gaps:", len(gap_index["gap_counts"]),
          "requirements:", len(requirement_index))
    for row in [c for c in consistency["checks"] if not c["ok"]]:
        print("CONSISTENCY FAIL:", row["check"])
        print("  expected:", row["expected"])
        print("  actual:  ", row["actual"])
    print("consistency all_ok:", consistency["all_ok"])
    return 0 if consistency["all_ok"] else 2


def main(argv=None):
    return run(parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
