#!/usr/bin/env python3
"""AP-10 lane tool: small deterministic regression selection per capability.

Implements AP-10 item 4: for every new native capability a small, concrete,
deterministic record set is selected from the committed static gap report
instead of executing the full corpus (foreign CT Lua/AA is never executed).
The selection is static data only: table, group, record id, name, status,
gaps, providers, target build.

Selection rule (documented, deterministic):
  1. match records against the capability contract
     (``--capability`` names one of CAPABILITIES; ``--all`` selects every
     capability); a record matches when its category is allowed (if the
     contract names categories) and at least one listed gap or provider
     applies (either list may be empty; at least one of them must not);
  2. within the matches, prefer status ``locked``, then
     ``statically_assumed``, then ``unknown`` (unknown stays flagged,
     never reinterpreted as an assumption);
  3. within a status rank keep the gap report document order
     (pinned table order, group order, record order);
  4. cap the selection at ``--max-per-capability`` records (default 8).

Output: ``regression-selection.json`` in ``--output`` with the selected
records per capability, the total match counts (so zero-match and capped
capabilities stay visible), and the source artifact hash.

Deterministic: same inputs + same run-id => byte-identical artifact (sorted
JSON keys, 1-space indent, no wall-clock timestamps; ``generated`` is the
documented run stamp ``"run <run-id>"``).

Exit codes: 0 ok, 1 input error, 2 unknown capability or nothing selected
without ``--all``, 3 write refused (never into the directory containing the
input artifact).

Usage:
  python tools/corpus_denominator/regression_selection.py \
      [--gap-report <path>] --output <out-dir> [--run-id <id>] \
      (--all | --capability <name> ...) [--max-per-capability N]
"""
import argparse
import hashlib
import json
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCHEMA_NAME = "corpus-regression-selection/v1"
DEFAULT_RUN_ID = "repo-reproducible"

_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(_PKG_DIR))
DEFAULT_GAP_REPORT = os.path.join(REPO_ROOT, "gap_inventory", "gap-report.json")

# Static capability contract: name -> matcher + documentation.
# 'categories' (optional): record.category must be one of these.
# 'gaps' / 'providers' (optional, at least one list non-empty): the record
# matches when at least one listed gap is in record.gaps or at least one
# listed provider is in record.providers.
CAPABILITIES = {
    "clock": {
        "description": "Clock/speedhack API (N-16; Alien Isolation, re2)",
        "match": {"gaps": ["lua_clock_speed"]},
    },
    "strings": {
        "description": "String records with bounded codec (N-18)",
        "match": {"categories": ["string_write"]},
    },
    "value_freeze": {
        "description": "Typed value records with freeze potential (N-05/N-06)",
        "match": {"categories": ["value_freeze"]},
    },
    "one_shot_state": {
        "description": "One-shot without ON/OFF save contract (state contract, AP-04)",
        "match": {"gaps": ["one_shot_save_contract"]},
    },
    "globalh3": {
        "description": "Globalalloc path (AP-08 Global; Trine 2, RDR2, re2, re4)",
        "match": {"gaps": ["aa_globalalloc_general"],
                  "providers": ["aa_globalalloc"]},
    },
    "mono_broker": {
        "description": "Mono/IL2CPP runtime access (N-12/N-13/N-14; Yooka-Laylee)",
        "match": {"gaps": ["lua_managed_runtime"]},
    },
    "il2cpp_resolver": {
        "description": "IL2CPP method resolution (N-12/N-13/N-14; Disco Elysium, Hellblade 2)",
        "match": {"gaps": ["managed_method_resolution"]},
    },
    "async_lifecycle": {
        "description": "Async record lifecycle (N-08; re2 et al.)",
        "match": {"gaps": ["async_lifecycle"]},
    },
    "parent_activation": {
        "description": "Parent/symbol activation (N-07; parent_ids, symbol chains)",
        "match": {"gaps": ["parent_activation", "recursive_parent_value",
                           "cross_record_symbol"]},
    },
    "custom_types": {
        "description": "Custom type codec (N-17; 3 pinned records)",
        "match": {"gaps": ["custom_type"]},
    },
    "scan_modes": {
        "description": "AOB scan modes (AP-08.5; process/module/region)",
        "match": {"providers": ["aob_scan_process", "aob_scan_module",
                                "aob_scan_region"]},
    },
    "dropdown_links": {
        "description": "Dropdown links to foreign records (N-18)",
        "match": {"gaps": ["dropdown_link"]},
    },
}

STATUS_RANK = {"locked": 0, "statically_assumed": 1, "unknown": 2}


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


def record_matches(spec, record):
    cats = spec.get("categories")
    if cats and record["category"] not in cats:
        return False
    gaps = spec.get("gaps")
    provs = spec.get("providers")
    if not (gaps or provs):
        return True
    if gaps and any(g in record["gaps"] for g in gaps):
        return True
    if provs and any(p in record.get("providers", []) for p in provs):
        return True
    return False


def matched_parts(spec, record):
    gaps = [g for g in spec.get("gaps", []) if g in record["gaps"]]
    provs = [p for p in spec.get("providers", [])
             if p in record.get("providers", [])]
    cats = ([record["category"]] if record["category"] in spec.get(
        "categories", []) else [])
    return {"gaps": gaps, "providers": provs, "categories": cats}


def select_capability(spec, gap_report, max_per):
    """Select up to ``max_per`` records for one capability (deterministic)."""
    matches = []
    seq = 0
    for table in gap_report["pinned_tables"]:
        for group in table["records_by_group"]:
            for rec in group["records"]:
                if record_matches(spec["match"], rec):
                    matches.append((seq, table, group, rec))
                seq += 1
    matches.sort(key=lambda m: (STATUS_RANK.get(m[3]["status"], 3), m[0]))
    selected = matches[:max_per]
    return {
        "description": spec["description"],
        "match": spec["match"],
        "match_total": len(matches),
        "capped": len(matches) > max_per,
        "selected_count": len(selected),
        "selected": [{
            "table": table["table"],
            "table_path": table["path"],
            "table_sha256": table["sha256"],
            "group": group["group"],
            "record_id": rec["id"],
            "record_name": rec["name"],
            "category": rec["category"],
            "status": rec["status"],
            "gaps": list(rec["gaps"]),
            "providers": list(rec.get("providers", [])),
            "architecture": rec.get("architecture"),
            "target_build": rec.get("target_build"),
            "matched": matched_parts(spec["match"], rec),
        } for _seq, table, group, rec in selected],
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="regression_selection",
        description="Small deterministic regression selection per capability "
                    "from the committed AP-10 gap report (read-only, static).")
    parser.add_argument("--gap-report", default=DEFAULT_GAP_REPORT,
                        help="path to gap-report.json (default: "
                             "repo gap_inventory/gap-report.json)")
    parser.add_argument("--output", default=None,
                        help="directory receiving regression-selection.json "
                             "(required unless --list)")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID,
                        help="deterministic run identifier carried in the "
                             "'generated' and 'run_id' fields")
    parser.add_argument("--capability", action="append", default=None,
                        help="capability name from CAPABILITIES "
                             "(repeatable; see --list)")
    parser.add_argument("--all", action="store_true",
                        help="select every defined capability")
    parser.add_argument("--max-per-capability", type=int, default=8,
                        help="maximum selected records per capability "
                             "(default: 8)")
    parser.add_argument("--list", action="store_true",
                        help="print the capability contract and exit")
    return parser.parse_args(argv)


def run(args):
    if args.list:
        for name in sorted(CAPABILITIES):
            print("%-18s %s" % (name, CAPABILITIES[name]["description"]))
        return 0
    if not args.list and not args.output:
        print("an output directory is required unless --list is used")
        return 2
    if args.max_per_capability < 1:
        print("--max-per-capability must be >= 1")
        return 2
    if not args.all and not args.capability:
        print("select at least one capability or use --all")
        return 2
    names = sorted(CAPABILITIES) if args.all else sorted(set(args.capability))
    unknown = [n for n in names if n not in CAPABILITIES]
    if unknown:
        print("unknown capability(ies):", unknown,
              "(known: %s)" % ", ".join(sorted(CAPABILITIES)))
        return 2

    try:
        gap_report = load_json(args.gap_report)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print("input error:", e)
        return 1
    if "pinned_tables" not in gap_report:
        print("gap report missing key: pinned_tables")
        return 1

    out_dir = os.path.abspath(args.output)
    if _refused(out_dir, [os.path.dirname(os.path.abspath(args.gap_report))]):
        print("refusing to write into the directory containing the "
              "input artifact:", args.output)
        return 3

    capabilities = {n: select_capability(CAPABILITIES[n], gap_report,
                                         args.max_per_capability)
                    for n in names}
    selected_keys = set()
    for cap in capabilities.values():
        for sel in cap["selected"]:
            selected_keys.add((sel["table_path"], sel["record_id"]))

    document = {
        "schema": SCHEMA_NAME,
        "generated": "run %s" % args.run_id,
        "run_id": args.run_id,
        "lane": "AP-10 static regression selection (no execution)",
        "source": {
            "gap_report": os.path.abspath(args.gap_report),
            "gap_report_sha256": sha256_file(args.gap_report),
        },
        "selection_rule": {
            "match": "category allowed AND (any listed gap OR any listed provider)",
            "order": "status rank locked < statically_assumed < unknown, then gap-report document order",
            "cap": "max_per_capability",
            "unknown_handling": "unknown records stay flagged; never reinterpreted",
        },
        "max_per_capability": args.max_per_capability,
        "capabilities": capabilities,
        "totals": {
            "capabilities": len(capabilities),
            "records_selected": sum(c["selected_count"]
                                    for c in capabilities.values()),
            "unique_records_selected": len(selected_keys),
            "zero_match_capabilities": sorted(
                n for n, c in capabilities.items() if c["match_total"] == 0),
            "capped_capabilities": sorted(
                n for n, c in capabilities.items() if c["capped"]),
        },
        "note": "Static selection from the committed gap report; no "
                "execution of CT Lua/AA, no corpus modifications.",
    }

    os.makedirs(out_dir, exist_ok=True)
    out = _write_json(out_dir, "regression-selection.json", document)
    print("wrote", out, os.path.getsize(out), "bytes")
    for name in names:
        cap = capabilities[name]
        print("%-18s match=%-5d selected=%d%s" % (
            name, cap["match_total"], cap["selected_count"],
            " (capped)" if cap["capped"] else ""))
    return 0


def main(argv=None):
    return run(parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
