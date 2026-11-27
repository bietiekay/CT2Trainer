"""Deep diff of two gc_replay.py JSON outputs (0.52.5 widened baseline).

Same 15 categories as gc_replay_diff.py, but the wishes comparison
ignores the traceback artifact: a failed wish's `trace` carries the
tree-specific absolute source path and line numbers, so two replays of
the SAME behaviour from different checkouts are not byte-equal in that
string.  The trace is normalized (absolute paths -> <src>/, line
numbers stripped) before the comparison; label and result are
compared strictly.  Tree-specific metadata (tree, ct2trainer_file) is
excluded.  Usage:
    python gc_replay_diff_norm.py <a.json> <b.json>
"""
import json
import re
import sys

a = json.load(open(sys.argv[1], encoding="utf-8"))
b = json.load(open(sys.argv[2], encoding="utf-8"))
diffs = 0


def check(name, va, vb):
    global diffs
    if va != vb:
        diffs += 1
        print("DIFF " + name)
        print("  a: " + json.dumps(va, ensure_ascii=False)[:3000])
        print("  b: " + json.dumps(vb, ensure_ascii=False)[:3000])
    else:
        print("OK   " + name)


def norm_trace(trace):
    if trace is None:
        return None
    t = re.sub(r'"[A-Za-z]:[^"]*?native[\\/]([^"\\]+\.py)"', r'"<src>/\1"', trace)
    t = re.sub(r'"[A-Za-z]:[^"]*\.py"', '"<src>/.py"', t)
    t = re.sub(r", line \d+, in ", ", in ", t)
    return t


wa = a["wishes"]
wb = b["wishes"]
wishes = {
    "keys": sorted(wa.keys()),
    "per-wish": {
        k: {
            "label": wa[k].get("label"),
            "result": wa[k].get("result"),
            "trace_norm": norm_trace(wa[k].get("trace")),
        }
        for k in sorted(wa.keys())
    },
}
wishes_b = {
    "keys": sorted(wb.keys()),
    "per-wish": {
        k: {
            "label": wb[k].get("label"),
            "result": wb[k].get("result"),
            "trace_norm": norm_trace(wb[k].get("trace")),
        }
        for k in sorted(wb.keys())
    },
}
check("wishes(label,result,normalized-trace)", wishes, wishes_b)

check("connected", a["connected"], b["connected"])
check("final", a["final"], b["final"])

# scans: (pattern, result, match_count) in call order
sa = [(s["pattern"], s["result"], s["match_count"]) for s in a["scans"]]
sb = [(s["pattern"], s["result"], s["match_count"]) for s in b["scans"]]
check("scans", sa, sb)

# writes: (addr, size, data, region) in call order
wa_ = [(w["addr"], w["size"], w["data"], w["region"]) for w in a["writes"]]
wb_ = [(w["addr"], w["size"], w["data"], w["region"]) for w in b["writes"]]
check("writes", wa_, wb_)

# resolutions: (expression, result) in call order
ra = [(r["expression"], r["result"]) for r in a["resolves"]]
rb = [(r["expression"], r["result"]) for r in b["resolves"]]
check("resolves", ra, rb)

# allocations: (size, near) in call order, then addresses in order
aa = [(x["size"], x["near"]) for x in a["allocs"]]
ab = [(x["size"], x["near"]) for x in b["allocs"]]
check("allocs(size,near)", aa, ab)
check("allocs(addrs)", [x["result"] for x in a["allocs"]],
      [x["result"] for x in b["allocs"]])

# allocation contents by relative slot order
ca = list(a["alloc_contents"].values())
cb = list(b["alloc_contents"].values())
check("alloc_contents", ca, cb)

check("module_diff", a["module_diff"], b["module_diff"])
check("module_diff_applied", a["module_diff_applied"],
      b["module_diff_applied"])
check("protects", a["protects"], b["protects"])
check("releases", a["releases"], b["releases"])
check("scan_counts", a["scan_counts"], b["scan_counts"])
check("read_counts", a["read_counts"], b["read_counts"])
check("holds", a["holds"], b["holds"])

# The canonical plan sha is reported but NOT counted as a difference:
# 0.42+ plans carry the (inert, empty) unowned_cleanup_dropped fields,
# which are a known, documented plan-shape delta.
print()
print("plan sha a: " + a.get("plan_canonical_sha256", "?"))
print("plan sha b: " + b.get("plan_canonical_sha256", "?"))
print()
print("TOTAL DIFFERENCES:", diffs)
