#!/usr/bin/env python3
"""AP-10 lane driver: hash-deduplicated CT corpus inventory + static gap report.

Read-only against the corpus (no modification, no execution of any CT Lua/AA
content). Stdlib only. Writes exactly, into the ``--output`` directory:
  inventory.json
  gap-report.json

Deterministic: same corpus + same run-id produce byte-identical artifacts
(sorted JSON keys, no wall-clock timestamps). The ``generated`` field is the
documented run stamp ``"run <run-id>"``; the reference artifacts under
``gap_inventory/`` embed the original lane run id in the same fields.

Usage:
  python tools/corpus_denominator/__main__.py \
      --corpus <corpus-root> --output <out-dir> [--run-id <id>]
"""
import argparse
import hashlib
import json
import os
import sys
import xml.etree.ElementTree as ET
from collections import Counter

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
try:
    from . import classify, scan, table
    from .lib import MODULE_REF
except ImportError:
    # Direct script execution: python tools/corpus_denominator/__main__.py
    if _PKG_DIR not in sys.path:
        sys.path.insert(0, _PKG_DIR)
    import classify
    import scan
    import table
    from lib import MODULE_REF

# Repository root = two levels above this package (<repo>/tools/corpus_denominator).
REPO_ROOT = os.path.dirname(os.path.dirname(_PKG_DIR))
REFERENCE_INVENTORY = os.path.join(REPO_ROOT, "tests", "fixtures",
                                   "reference-inventory.json")

# Pinned start corpus (AP-10): 14 tables, 7 of them byte-pinned in
# tests/fixtures/reference-inventory.json. Paths relative to the corpus root, "/".
PINNED = [
    "case-01.ct",
    "case-02.ct",
    "case-03.ct",
    "case-04.ct",
    "case-05.ct",
    "case-06.ct",
    "case-07.ct",
    "case-08.ct",
    "case-09.ct",
    "case-10.ct",
    "case-11.ct",
    "case-12.ct",
    "case-13.ct",
    "case-14.ct",
    "case-19.ct",
]

# gap id -> (label, requirement/package mapping)
GAP_LABELS = {
    "lua_host_profile": ("Lua host profile (bounded Lua host profile)", "N-01 / N-19"),
    "lua_record": ("Lua record without executed proof", "N-01 / N-19"),
    "lua_record_body": ("Lua body on the record (no runtime)", "N-01 / N-19"),
    "table_lua_lifecycle": ("Table Lua lifecycle (loads on import)", "N-19"),
    "lua_managed_runtime": ("Mono/IL2CPP runtime access", "N-12 / N-13 / N-14"),
    "managed_method_resolution": ("Managed method resolution (IL2CPP injection labels)", "N-12 / N-13 / N-14"),
    "lua_typed_target_call": ("Typed target API calls (executeCode ...)", "N-14"),
    "aa_createthread_threadwait": ("AA thread control (createThread/threadWait)", "N-15"),
    "aa_target_api_binding": ("Target API binding (GetProcAddress/GetModuleHandle)", "AP-02 / AP-06"),
    "aa_debugger_api": ("AA disassembler API", "AP-02"),
    "aa_nested_script": ("Nested autoAssemble() scripts", "AP-02"),
    "aa_protection_control": ("AA memory protection (protect/unprotect)", "AP-02"),
    "aa_luacall": ("AA Lua calls (luacall)", "N-01 / N-19"),
    "aa_conditional_block": ("AA {$if} blocks (not delimited by content)", "AP-02"),
    "aa_sections_incomplete": ("Incomplete ENABLE/DISABLE sections", "AP-02 / state contract"),
    "aa_directive_unverified": ("Unverified AA directives (residual tokens)", "AP-02"),
    "aa_globalalloc_general": ("Globalalloc beyond the literal path", "AP-08 (Global)"),
    "async_lifecycle": ("Async record lifecycle", "N-08"),
    "custom_type": ("Custom type codec", "N-17"),
    "string_codepage": ("String codepage encoding", "N-18"),
    "dropdown_link": ("Dropdown link to foreign records", "N-18"),
    "parent_activation": ("Group/parent activation option", "N-07"),
    "recursive_parent_value": ("Recursive parent value (moRecursiveSetValue)", "N-07"),
    "cross_record_symbol": ("Cross-record symbol resolution", "N-07"),
    "one_shot_save_contract": ("One-shot without ON/OFF save contract", "state contract (AP-04)"),
    "script_parent_activation": ("Script parent with child-activation propagation (staged unlock)", "WP-14 (extends AP-07)"),
    "record_activation_set": ("Embedded-Lua master toggle (record-ID activation sets)", "WP-14"),
    "signed_pointer_offset": ("Signed pointer-offset literal (`+`/`-` in `<Offsets>`)", "WP-14 (format contract)"),
    "lua_clock_speed": ("Clock/speedhack API", "N-16"),
    "lua_worker_thread": ("Lua worker threads", "N-15"),
    "lua_gui_api": ("Lua GUI API (showMessage/Forms)", "N-21"),
    "lua_process_api": ("Lua process API", "N-15 / AP-06"),
    "lua_symbol_api": ("Lua symbol API", "N-07 / N-19"),
    "lua_ce_engine_api": ("CE Lua engine API", "N-19"),
    "lua_debugger_api": ("Lua debugger API", "AP-02"),
    "lua_dynamic_assembler": ("Dynamic Lua autoAssemble calls", "AP-02 / N-19"),
    "value_address_empty": ("Value record without address", "N-05"),
    "address_form_unrecognized": ("Unknown address form", "N-05"),
    "record_unclassifiable": ("Unclassifiable record", "N-05 / N-24"),
}

MISSING_GATES = [
    "Real game installs/builds for the 15 pinned tables (user question unanswered)",
    "Actual game effect (ON/OFF, values, freeze, target/controller restart)",
    "VM/Clean-PC gate without CE/Python",
    "Real Steam Deck with Proton prefix (touch/screenkeyboard/state/freeze/clock)",
    "Table-level completeness per table (forms, Lua lifecycle, custom types, assets)",
    "Frozen/binary proof (source-only evidence of this lane)",
    "Reproducibility with exact commands and pinned inputs",
]


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def collect_files(root):
    out = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in filenames:
            if fn.lower().endswith(".ct"):
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, root).replace("\\", "/")
                out.append((rel, full))
    return sorted(out)


def _int_or_none(raw):
    try:
        return int((raw or "").strip())
    except (TypeError, ValueError):
        return None


def record_target_build(rec, modules):
    cat = rec["category"]
    ak = rec.get("address_kind")
    if cat == "navigation":
        return "no_own_target"
    if ak == "fixed":
        return "build_bound_fixed_address"
    if ak == "managed":
        base = "managed_module_binding"
        return base + (":" + ",".join(modules[:3]) if modules else "")
    if modules:
        return "module_binding:" + ",".join(modules[:3])
    if ak in ("process", "relative", "expression"):
        return "process_relative"
    if ak in ("symbol", "symbol_ud"):
        return "table_symbols"
    if ak in ("empty", "unresolved") or ak is None:
        return "unresolved"
    return "process_portable"


def analyze_table(sha, rel, data):
    info = {
        "sha256": sha,
        "size_bytes": len(data),
        "paths": [rel],
        "primary_path": rel,
        "xml_parsable": True,
        "parse_error": None,
        "root_tag": None,
        "format_version": None,
        "sections": None,
        "entries_total": None,
        "groups": None,
        "records": None,
        "duplicate_ids": None,
        "record_types": None,
        "categories": None,
        "status_counts": None,
        "gap_counts": None,
        "table_flags": None,
        "architecture": None,
        "module_refs": None,
        "group_toggle_actions": None,
    }
    try:
        root = ET.fromstring(data)
    except Exception as e:  # ParseError or worse; per-file error, not fatal
        info["xml_parsable"] = False
        info["parse_error"] = "%s: %s" % (type(e).__name__, e)
        info["duplicate_ids"] = {}
        return info, [], []

    info["root_tag"] = root.tag
    info["format_version"] = root.attrib.get("CheatEngineTableVersion")
    info["sections"] = sorted({c.tag for c in root})
    all_entries = list(root.iter("CheatEntry"))
    info["entries_total"] = len(all_entries)
    id_counts = Counter()
    for e in all_entries:
        i = _int_or_none(e.findtext("ID"))
        if i is not None:
            id_counts[i] += 1
    info["duplicate_ids"] = {str(k): v for k, v in sorted(id_counts.items()) if v > 1}
    info["table_flags"] = table.table_flags(root)

    ud = table.user_defined_symbol_names(root)
    records = []
    scans = []
    all_modules = set()
    # WP-25 alignment: the product plan is ID-keyed and keeps the first
    # occurrence of a duplicated CheatEntry ID.  The dropped duplicates are
    # not addressable actions, so the record walk skips them (keep-first,
    # document order) exactly like the product reader does.
    seen_record_ids = set()
    for entry, depth, labels, group_labels in table.iter_records(root):
        record_id = _int_or_none(entry.findtext("ID"))
        if record_id is not None:
            if record_id in seen_record_ids:
                continue
            seen_record_ids.add(record_id)
        rec = classify.classify_record(entry, ud)
        rec["depth"] = depth
        chain = list(labels)
        rec["group_chain"] = list(group_labels)
        rec["parent"] = chain[depth - 1] if depth > 0 else None
        script_el = entry.find("AssemblerScript")
        script = (script_el.text or "") if script_el is not None else ""
        rec_scan = None
        if rec["type"].startswith("aa_script"):
            rec_scan = scan.scan_aa(script)
            scans.append(rec_scan)
        mods = set()
        if rec_scan:
            mods |= set(rec_scan["modules"])
        addr = (entry.findtext("Address") or "").strip()
        if addr:
            mods |= {m.lower() for m in MODULE_REF.findall(addr)}
        rec["_modules"] = sorted(mods)
        all_modules |= mods
        rec["_scan"] = rec_scan
        records.append(rec)

    table_arch = table.architecture_hints(
        os.path.basename(rel), sorted(all_modules), scans)
    info["architecture"] = table_arch
    info["module_refs"] = sorted(all_modules)

    # finalize per-record architecture / target_build, strip internal keys
    for rec in records:
        rec_scan = rec.pop("_scan")
        if rec_scan:
            i64, i32 = rec_scan["instr64_lines"], rec_scan["instr32_lines"]
            if i64 and i32:
                rec["architecture"] = "mixed"
            elif i64:
                rec["architecture"] = "x64"
            elif i32:
                rec["architecture"] = "x86"
            else:
                rec["architecture"] = table_arch["value"]
        else:
            rec["architecture"] = table_arch["value"]
        rec["target_build"] = record_target_build(rec, rec.pop("_modules"))

    groups = []
    for entry, depth, path, _children, descendants in table.iter_groups(root):
        gt = table.group_toggle(entry, descendants)
        groups.append({
            "name": path[-1] if path else "",
            "path": " / ".join(path),
            "depth": depth,
            "has_checkbox": gt["has_checkbox"],
            "on_effect": gt["on_effect"],
            "group_action": gt["action"],
            "descendant_records": len(descendants),
        })
    info["group_toggle_actions"] = sum(1 for g in groups if g["group_action"])

    # records stay in document order; report output sorts a copy
    info["groups"] = len(groups)
    info["records"] = len(records)
    return info, records, groups


def top_gaps(counter, limit=10):
    out = []
    for gap, n in counter.most_common(limit):
        label, req = GAP_LABELS.get(gap, (gap, "unmapped"))
        out.append({"gap": gap, "affected_records": n,
                    "label": label, "requirement": req})
    return out


def table_report(display, info, records, groups, ref_entry, rel):
    status = Counter(r["status"] for r in records)
    cat = Counter(r["category"] for r in records)
    gaps = Counter()
    for r in records:
        for g in r["gaps"]:
            gaps[g] += 1
    navigation = cat.get("navigation", 0)
    expected = len(records) - navigation
    sorted_records = sorted(records, key=lambda r: (
        r["id"] is None, r["id"] if r["id"] is not None else 0))
    recs_by_group = []
    # records are grouped by their CE breadcrumb (chain of containing group
    # headers). Records with no group ancestors are grouped by their direct
    # parent label as "(direct: <parent>)", or "(direct: root)" when top-level.
    order = []
    for r in records:
        key = (" / ".join(r["group_chain"]) if r["group_chain"]
               else "(direct: " + (r["parent"] or "root") + ")")
        if key not in order:
            order.append(key)
    by_group = {}
    for r in sorted_records:
        key = (" / ".join(r["group_chain"]) if r["group_chain"]
               else "(direct: " + (r["parent"] or "root") + ")")
        by_group.setdefault(key, []).append(r)
    for p in order:
        recs_by_group.append({
            "group": p,
            "records": [{
                "id": r["id"],
                "name": r["name"],
                "type": r["type"],
                "category": r["category"],
                "status": r["status"],
                "gaps": r["gaps"],
                "providers": r["providers"],
                "lifetime": r.get("lifetime"),
                "architecture": r["architecture"],
                "target_build": r["target_build"],
                "semantics": r["semantics"],
                "parent": r["parent"],
                "depth": r["depth"],
                "async": r.get("async"),
                "address_kind": r.get("address_kind"),
            } for r in by_group[p]],
        })

    table_entry = {
        "table": display,
        "path": rel,
        "sha256": info["sha256"],
        "size_bytes": info["size_bytes"],
        "paths": info["paths"],
        "format_version": info["format_version"],
        "table_flags": info["table_flags"],
        "main_initialization": table.main_initialization(records, info["table_flags"]["table_lua"]),
        "architecture": info["architecture"],
        "counts": {
            "entries_total": info["entries_total"],
            "groups": info["groups"],
            "records": info["records"],
            "navigation_excluded": navigation,
            "expected_actions": expected,
            "group_toggle_actions": info["group_toggle_actions"],
            "record_types": dict(sorted((k, v) for k, v in Counter(r["type"] for r in records).items())),
            "categories": dict(sorted((k, v) for k, v in cat.items())),
            "status_counts": dict(sorted(status.items())),
            "gap_counts": dict(sorted(gaps.items())),
        },
        "duplicate_ids": info["duplicate_ids"],
        "groups": groups,
        "records_by_group": recs_by_group,
        "top_gaps": top_gaps(gaps, 10),
    }
    if ref_entry is not None:
        table_entry["reference"] = ref_entry
    return table_entry


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="corpus_denominator",
        description="Deterministic, read-only static inventory + gap report "
                    "for a Cheat Engine .CT corpus (AP-10 denominator).")
    parser.add_argument("--corpus", required=True,
                        help="corpus root directory containing .CT files (read-only)")
    parser.add_argument("--output", required=True,
                        help="directory receiving inventory.json and gap-report.json")
    parser.add_argument("--run-id", default="repo-reproducible",
                        help="deterministic run identifier carried in the "
                             "'generated' and 'run_id' fields "
                             "(default: repo-reproducible)")
    return parser.parse_args(argv)


def run(args):
    corpus_root = os.path.normpath(args.corpus)
    out_dir = os.path.abspath(args.output)
    run_id = args.run_id
    if not os.path.isdir(corpus_root):
        print("corpus root is not a directory:", args.corpus)
        return 1
    # Hard read-only corpus rule: never write into (or on top of) the corpus.
    same = out_dir.lower() == corpus_root.lower()
    inside = out_dir.lower().startswith(corpus_root.lower() + os.sep)
    if same or inside:
        print("refusing to write into the read-only corpus:", args.output)
        return 1

    files = collect_files(corpus_root)
    by_hash = {}
    for rel, full in files:
        with open(full, "rb") as f:
            data = f.read()
        h = sha256_bytes(data)
        slot = by_hash.setdefault(h, {"data": data, "paths": []})
        slot["paths"].append(rel)

    pinned_info = []
    missing = []
    for p in PINNED:
        full = os.path.join(corpus_root, p.replace("/", os.sep))
        if not os.path.exists(full):
            missing.append(p)
            continue
        with open(full, "rb") as f:
            data = f.read()
        pinned_info.append({"path": p, "sha256": sha256_bytes(data), "size": len(data)})
    if missing:
        print("PINNED PATHS MISSING:", missing)
        return 1

    tables = []
    rec_store = {}
    grp_store = {}
    for h, slot in by_hash.items():
        rel = sorted(slot["paths"])[0]
        info, records, groups = analyze_table(h, rel, slot["data"])
        slot["paths"].sort()
        info["paths"] = slot["paths"]
        info["primary_path"] = rel
        tables.append(info)
        rec_store[h] = records
        grp_store[h] = groups

    tables.sort(key=lambda t: (t["xml_parsable"] is False, t["primary_path"]))

    # ---- reference inventory verification -------------------------------
    with open(REFERENCE_INVENTORY, "r", encoding="utf-8") as f:
        ref_inv = json.load(f)
    reference_verification = {}
    ref_by_hash = {}
    for name, spec in sorted(ref_inv.items()):
        matches = [t for t in tables
                   if os.path.basename(t["primary_path"]) == name]
        if not matches:
            reference_verification[name] = {
                "expected_sha256": spec["sha256"], "computed_sha256": None,
                "hash_match": False, "expected_cheat_entries": spec["cheat_entries"],
                "computed_entries_total": None, "entry_match": False,
                "note": "file not found in corpus"}
            continue
        t = matches[0]
        ok_hash = t["sha256"] == spec["sha256"]
        ok_entries = (t["entries_total"] == spec["cheat_entries"])
        reference_verification[name] = {
            "expected_sha256": spec["sha256"],
            "computed_sha256": t["sha256"],
            "hash_match": ok_hash,
            "expected_cheat_entries": spec["cheat_entries"],
            "computed_entries_total": t["entries_total"],
            "entry_match": ok_entries,
            "path": t["primary_path"],
        }
        if ok_hash:
            ref_by_hash[t["sha256"]] = reference_verification[name]
    ref_ok = all(v["hash_match"] and v["entry_match"] for v in reference_verification.values())

    # ---- inventory.json ---------------------------------------------------
    inv_tables = []
    for t in tables:
        e = {k: t[k] for k in (
            "sha256", "size_bytes", "paths", "primary_path", "xml_parsable",
            "parse_error", "root_tag", "format_version", "sections",
            "entries_total", "groups", "records", "duplicate_ids",
            "record_types", "categories", "status_counts", "gap_counts",
            "table_flags", "architecture", "module_refs",
            "group_toggle_actions")}
        if t["xml_parsable"]:
            e["groups"] = len(grp_store[t["sha256"]])
            e["records"] = len(rec_store[t["sha256"]])
            e["record_types"] = dict(sorted(Counter(r["type"] for r in rec_store[t["sha256"]]).items()))
            e["categories"] = dict(sorted(Counter(r["category"] for r in rec_store[t["sha256"]]).items()))
            e["status_counts"] = dict(sorted(Counter(r["status"] for r in rec_store[t["sha256"]]).items()))
            gaps = Counter()
            for r in rec_store[t["sha256"]]:
                for g in r["gaps"]:
                    gaps[g] += 1
            e["gap_counts"] = dict(sorted(gaps.items()))
        else:
            for k in ("groups", "records", "record_types", "categories",
                      "status_counts", "gap_counts", "table_flags",
                      "architecture", "module_refs", "group_toggle_actions"):
                e[k] = None
        inv_tables.append(e)

    parseable = [t for t in tables if t["xml_parsable"]]
    all_records = [r for t in parseable for r in rec_store[t["sha256"]]]
    all_groups = [g for t in parseable for g in grp_store[t["sha256"]]]
    inv_totals = {
        "unique_tables": len(tables),
        "parseable_tables": len(parseable),
        "parse_errors": len(tables) - len(parseable),
        "entries_total": sum(t["entries_total"] for t in parseable),
        "groups": len(all_groups),
        "records": len(all_records),
        "navigation": sum(1 for r in all_records if r["category"] == "navigation"),
        "expected_actions": sum(1 for r in all_records if r["category"] != "navigation"),
        "group_toggle_actions": sum(1 for g in all_groups if g["group_action"]),
        "status_counts": dict(sorted(Counter(r["status"] for r in all_records).items())),
        "record_types": dict(sorted(Counter(r["type"] for r in all_records).items())),
        "gap_counts": dict(sorted(Counter(g for r in all_records for g in r["gaps"]).items())),
    }

    # deterministic run stamp (run id only) so identical inputs produce
    # byte-identical artifacts with stable SHA-256
    inventory = {
        "generated": "run %s" % run_id,
        "run_id": run_id,
        "lane": "AP-10 corpus inventory (read-only static analysis)",
        "corpus_root": corpus_root,
        "file_count": len(files),
        "unique_table_count": len(tables),
        "parse_error_count": len(tables) - len(parseable),
        "method": {
            "dedup": "SHA-256 per file; identical bytes counted once, all paths kept",
            "parsing": "xml.etree stdlib; per-file parse errors recorded, not fatal",
            "no_execution": "CT Lua/AA bodies are never executed; only static token classification",
            "entry_counts": "entries_total = every CheatEntry node; groups = GroupHeader=1; records = remainder",
            "navigation": "records with null/empty base address are null-array placeholders (no own effect)",
        },
        "reference_verification": reference_verification,
        "reference_verification_all_ok": ref_ok,
        "tables": inv_tables,
        "totals": inv_totals,
    }

    # ---- gap-report.json ---------------------------------------------------
    pinned_by_hash = {p["sha256"]: p for p in pinned_info}
    report_tables = []
    for p in pinned_info:
        h = p["sha256"]
        t = next(x for x in tables if x["sha256"] == h)
        display = os.path.dirname(p["path"]).replace("\\", "/") or os.path.basename(p["path"])
        if display == "":
            display = os.path.splitext(os.path.basename(p["path"]))[0]
        ref_entry = None
        for name, spec in sorted(ref_inv.items()):
            if os.path.basename(t["primary_path"]) == name:
                ref_entry = {
                    "pinned": True,
                    "reference_file": "tests/fixtures/reference-inventory.json",
                    "hash_match": t["sha256"] == spec["sha256"],
                    "cheat_entries_pinned": spec["cheat_entries"],
                    "cheat_entries_computed": t["entries_total"],
                    "entry_match": t["entries_total"] == spec["cheat_entries"],
                }
                break
        report_tables.append(table_report(display, t, rec_store[h], grp_store[h],
                                          ref_entry, t["primary_path"]))

    pinned_hashes = set(pinned_by_hash)
    rest_tables = [t for t in tables if t["sha256"] not in pinned_hashes]
    rest_records = [r for t in rest_tables if t["xml_parsable"] for r in rec_store[t["sha256"]]]
    rest_groups = [g for t in rest_tables if t["xml_parsable"] for g in grp_store[t["sha256"]]]
    rest_gaps = Counter()
    for r in rest_records:
        for g in r["gaps"]:
            rest_gaps[g] += 1
    corpus_rest = {
        "unique_tables": len(rest_tables),
        "parseable_tables": sum(1 for t in rest_tables if t["xml_parsable"]),
        "parse_errors": sum(1 for t in rest_tables if not t["xml_parsable"]),
        "entries_total": sum(t["entries_total"] for t in rest_tables if t["xml_parsable"]),
        "groups": len(rest_groups),
        "records": len(rest_records),
        "navigation": sum(1 for r in rest_records if r["category"] == "navigation"),
        "expected_actions": sum(1 for r in rest_records if r["category"] != "navigation"),
        "group_toggle_actions": sum(1 for g in rest_groups if g["group_action"]),
        "status_counts": dict(sorted(Counter(r["status"] for r in rest_records).items())),
        "gap_counts": dict(sorted(rest_gaps.items())),
        "top_gaps": top_gaps(rest_gaps, 10),
    }

    pinned_records = [r for p in pinned_info for r in rec_store[p["sha256"]]]
    pinned_groups = [g for p in pinned_info for g in grp_store[p["sha256"]]]
    pinned_gaps = Counter()
    for r in pinned_records:
        for g in r["gaps"]:
            pinned_gaps[g] += 1
    pinned_nav = sum(1 for r in pinned_records if r["category"] == "navigation")
    pinned_expected = len(pinned_records) - pinned_nav

    denominator = {
        "scope": "15 pinned start-corpus tables (hash-deduplicated, static)",
        "unique_tables": len(pinned_info),
        "records_total": len(pinned_records),
        "navigation_excluded": pinned_nav,
        "expected_actions": pinned_expected,
        "groups_total": len(pinned_groups),
        "group_toggle_actions": sum(1 for g in pinned_groups if g["group_action"]),
        "status_counts": dict(sorted(Counter(r["status"] for r in pinned_records).items())),
        "category_counts": dict(sorted(Counter(r["category"] for r in pinned_records).items())),
        "record_types": dict(sorted(Counter(r["type"] for r in pinned_records).items())),
        "confirmed_game_effect_actions": 0,
        "confirmed_percent": 0.0,
        "goal_90_percent": "NOT REACHED",
        "separation": {
            "static_assumed": "assessed as possible statically only, no runtime proof",
            "locked": "requires a missing API/feature; not fulfillable without it",
            "unknown": "stays unknown; no reinterpretation as success cheats",
            "synthetic": "fixture/mock proofs do not count as game effect",
            "real_game_effect": "0 actions with observed real game effect",
        },
        "missing_gates": MISSING_GATES,
    }

    top_pinned = []
    for gap, n in pinned_gaps.most_common(10):
        label, req = GAP_LABELS.get(gap, (gap, "unmapped"))
        share = round(100.0 * n / pinned_expected, 2) if pinned_expected else 0.0
        top_pinned.append({"gap": gap, "affected_records": n,
                           "share_of_expected_actions_percent": share,
                           "label": label, "requirement": req})

    gap_report = {
        "generated": inventory["generated"],
        "run_id": run_id,
        "lane": "AP-10 static gap report (read-only, no script execution)",
        "counting_convention": {
            "expected_actions": "records minus navigation (null arrays/placeholders do not count as actions)",
            "groups": "counted separately, not as record actions",
            "group_toggles": "group checkbox with a CE own effect: own locked bucket, no record action",
            "statuses": "statically_assumed / locked / unknown; unknown stays unknown",
            "confirmed": "no real game effect in this lane => confirmed = 0",
        },
        "gap_labels": {k: {"label": v[0], "requirement": v[1]} for k, v in sorted(GAP_LABELS.items())},
        "pinned_tables": report_tables,
        "corpus_rest": corpus_rest,
        "denominator": denominator,
        "top_gaps_pinned": top_pinned,
    }

    os.makedirs(out_dir, exist_ok=True)
    for name, obj in (("inventory.json", inventory), ("gap-report.json", gap_report)):
        out = os.path.join(out_dir, name)
        # newline="\n" keeps committed baselines byte-identical on every
        # platform (text-mode writes would translate to CRLF on Windows).
        with open(out, "w", encoding="utf-8", newline="\n") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1, sort_keys=True)
            f.write("\n")
        print("wrote", out, os.path.getsize(out), "bytes")

    # console summary for the run log
    print("files:", len(files), "unique:", len(tables),
          "parse_errors:", len(tables) - len(parseable))
    print("reference_verification_all_ok:", ref_ok)
    print("pinned records:", len(pinned_records), "nav:", pinned_nav,
          "expected_actions:", pinned_expected,
          "groups:", len(pinned_groups),
          "group_toggles:", denominator["group_toggle_actions"])
    print("top pinned gaps:")
    for row in top_pinned:
        print("  %-28s %4d  %5.2f%%  %s" % (
            row["gap"], row["affected_records"],
            row["share_of_expected_actions_percent"], row["requirement"]))
    return 0


def main(argv=None):
    return run(parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
