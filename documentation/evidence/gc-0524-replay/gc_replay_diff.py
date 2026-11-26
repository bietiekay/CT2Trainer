"""Deep diff of two gc_replay.py JSON outputs (0.41 vs the 0.52.3 baseline).

Usage: python gc_replay_diff.py <a.json> <b.json> [summary.txt]

The wishes comparison is semantic (label + result per entry): the
harness-embedded Python traceback strings differ by worktree path and
line numbers between trees and are not target traffic.  An optional
third argument writes the summary to that file as UTF-8.
"""
import json
import sys

a = json.load(open(sys.argv[1], encoding="utf-8"))
b = json.load(open(sys.argv[2], encoding="utf-8"))
diffs = 0
lines = []


def check(name, va, vb):
    global diffs
    if va != vb:
        diffs += 1
        print("DIFF " + name)
        print("  041: " + json.dumps(va, ensure_ascii=False)[:3000])
        print("  main: " + json.dumps(vb, ensure_ascii=False)[:3000])
        lines.append("DIFF " + name)
    else:
        print("OK   " + name)
        lines.append("OK   " + name)


def wish_view(wishes):
    return {str(k): {key: v[key] for key in ("label", "result")}
            for k, v in wishes.items()}


check("connected", a["connected"], b["connected"])
check("wishes", wish_view(a["wishes"]), wish_view(b["wishes"]))
check("final", a["final"], b["final"])

# scans: (pattern, result, match_count) in call order
sa = [(s["pattern"], s["result"], s["match_count"]) for s in a["scans"]]
sb = [(s["pattern"], s["result"], s["match_count"]) for s in b["scans"]]
check("scans", sa, sb)

# writes: (addr, size, data, region) in call order
wa = [(w["addr"], w["size"], w["data"], w["region"]) for w in a["writes"]]
wb = [(w["addr"], w["size"], w["data"], w["region"]) for w in b["writes"]]
check("writes", wa, wb)

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

print()
print("TOTAL DIFFERENCES:", diffs)
