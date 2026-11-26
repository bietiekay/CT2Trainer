# Great Circle crash case — static replay proof (0.52.4)

Field case: every trainer build after 0.41 crashed "Indiana Jones and the
Great Circle" ~60–77 s after attach while the trainer sat
read-only-idle. The game build is unchanged and worked with the 0.41
trainer. This directory holds the deterministic replay that answers the
question "is the trainer's target traffic different?" for that table.

## Verdict

**No trainer-side target-traffic difference.** The 0.41 code
(`main` @ `c724a7e`, build `native-20261110T210856Z-5811040c`) and the
0.52.3 code (`main` @ `421d7c7`, build
`native-20261126T030208Z-a082e323`) produce byte-identical target
operations for the failing table and the field wish set
`[1, 6, 7, 12, 13, 16, 19, 20, 21, 24, 31]`:

- 22 scans — identical patterns, match counts, first-match addresses,
  order;
- 34 writes — 22 module patches + 12 cave writes, identical
  address/size/data in the same order;
- 6 allocations — identical sizes and near-targets, deterministic
  addresses, identical contents;
- 0 resolves, identical protects/releases, identical `scan_counts` /
  `read_counts`;
- 11 applied patch ranges, identical before/after bytes (stealth
  mode prefix-cut, health, reload x2, oxygen, use-item, currency,
  ammo, durability, stamina, food);
- clean close: post-close module diff = 0, `applied: []`,
  `blocked: false` in both runs;
- entries 6 / 16 (the alternate A/B builds) miss their scan in both
  runs — the documented by-design ScanMiss, identical in both trees.

`diff-summary.txt` is the full comparison output
(`TOTAL DIFFERENCES: 0`).

The compiled plans are functionally identical as well: the 0.52.3 plan
differs from the 0.41 plan only by 15 empty
`unowned_cleanup_dropped: []` markers added by the 0.42 cleanup-parity
change (inert for this table) plus generation metadata.

## What the replay proves and what it cannot prove

Proves: for this table, the *content and order* of every read, scan,
write, allocation, protection and restore the trainer performs is
unchanged between 0.41 and 0.52.3. A crash caused by the trainer
*writing different bytes, to different addresses, in a different
order* is ruled out.

Cannot prove: timing/environment differences (thread schedules, page
fault timing, allocator addresses on a real machine — the replay uses
synthetic module base `0x140000000`, module size 122,609,664, field
module base was `0x7ff70b2a0000`; field field-addresses =
`0x7ff70b2a0000 + rva`), and non-memory causes (e.g. the hotkey bridge
threads, OS-level events). The 0.52.4 forensics events
(`entry-applied` with exact patch ranges + cave contents,
`rearm-attempt` with `duration_ms` + `scan_range`) are the follow-up
instrumentation so the next field crash yields a cross-referenceable
record.

## Inputs

- Table (local-only, not distributable, referenced by sha256):
  `TheGreatCircle_Plus21_extracted.ct`
  `4e0dc0b54a5d96526d680042fe323bcfc4421327559c201f0b688279fff18c2b`
  (46 entries, pure Auto Assembler, process `TheGreatCircle.exe`).
- Synthetic module image: filler `0xEE`; the 11 known AOB patterns
  from the 0.52.2 field log planted at their exact field RVAs
  (`PLACEMENTS` in `gc_replay.py` — the 9 enabled wishes scan 11
  anchors because No Reload and Items Won't Decrease each carry
  two); `aobhealth2` / `aobammo2` deliberately absent → ScanMiss, as
  observed in the field.
- Fixed identity: PID 424242, creation time 134399935579190145,
  pointer size 8.

## Regenerating

```
set CT2TRAINER_NASM=<repo>\.tools\native\nasm-3.02\nasm-3.02\nasm.exe
python gc_replay.py <tree_at_c724a7e>  <table.ct> out-041.json
python gc_replay.py <tree_at_421d7c7> <table.ct> out-main.json
python gc_replay_diff.py out-041.json out-main.json diff-summary.txt
```

The harness is self-contained apart from the tree-under-test's
`src/` (pinned NASM required) and the local table file.

## Artifacts

| file | content |
|------|---------|
| `gc_replay.py` | deterministic replay harness (parameterized) |
| `gc_replay_diff.py` | deep diff of two replay outputs |
| `replay-041.json` | replay at 0.41 (`main` @ `c724a7e`) |
| `replay-main.json` | replay at 0.52.3 (`main` @ `421d7c7`) |
| `diff-summary.txt` | full comparison, `TOTAL DIFFERENCES: 0` |
| `steady-tick-path-diff.txt` | 0.41 vs 0.52.3 steady-state tick / verification / value-read path diff (the crash window is read-only-idle; only the 0.43 transient-read-skip handling differs - read-side error path, fail-closed) |
