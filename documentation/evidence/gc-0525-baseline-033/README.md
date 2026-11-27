# Great Circle crash case — 0.33 baseline proof (0.52.5)

Field case: every trainer build after the 0.3x era crashed "Indiana Jones
and the Great Circle" ~60–77 s after attach while the trainer sat
read-only-idle; the game build is unchanged and worked with the older
trainers. The 0.52.4 release proved that the **0.41** vs **0.52.3** target
traffic is byte-identical (`documentation/evidence/gc-0524-replay/`). This
directory widens the proof back to the **0.33** baseline — the last release
line **before the 0.39 bounded transient-read retry** landed in
`memory._read_exact` — because the field report ("it worked before 0.4/0.5")
points at the 0.3x era as the last known-good window.

## Verdict

**0.33 and current `main` produce identical target traffic for this
table and the field wish set `[1, 6, 7, 12, 13, 16, 19, 20, 21, 24, 31]`.**

- The 0.33 plan is byte-identical to the 0.41 plan (canonical sha
  `33fba361396b8ad11e0c97d188be61b0426e140c4b73c159db6c2ba52bcc416f` in
  both replay outputs); the 0.33→main plan delta is only the 15 empty
  `unowned_cleanup_dropped: []` fields added by the 0.42 cleanup-parity
  change (inert for this table; `plan-diff-041-main.txt`, canonical sha
  of main `bbf91f7cf9810d3367a1e1ff846ead49e2c3327559d8365130002c42f4e6df45`).
- Normalized replay deep-diff 0.33 vs 0.41: **TOTAL DIFFERENCES: 0**
  (`diff-norm-033-041.txt`).
- Normalized replay deep-diff 0.33 vs current main: **TOTAL DIFFERENCES: 0**
  (`diff-norm-033-main.txt`) — 22 scans (identical patterns / match counts /
  order), 34 writes, 6 allocations (identical sizes, near-targets, contents),
  0 resolves, identical protects/releases/holds, identical `scan_counts`
  (24) / `read_counts` (1005), identical module diff (0 applied ranges,
  clean close: `applied: []`, `blocked: false`); entries 6 / 16 miss their
  scan in every run (the documented by-design ScanMiss). The wishes
  comparison is strict on label and result; only the tree-specific
  traceback path/line-number artifact of the two failed wishes is
  normalized away.
- The 0.33→main window touched 46 files (`window-033-main-filestat.txt`);
  the only target-touching behaviour delta in it is the 0.39 bounded
  transient-read retry. The coordinator/hook diffs
  (`diff-033-043-coord.txt`, `diff-043-0523-coord.txt`) are
  failure-path / validation-path only (transient re-raise in the hook
  guard; direction-aware prefix-cut close validation from 0.52.3).

## Consequence for the 0.52.5 fix

Before 0.39 a transient `ReadProcessMemory` failure inside the bounded
rearm module scan aborted the scan on the **first** attempt; from 0.39 on
the same failure triggered up to **4 reads plus 0.05→0.25 s backoff
sleeps under the memory lock**, per chunk — now also for the 122 MB GC
module scan. That is the one new target-touching behaviour in the whole
0.33→0.52.3 window. The 0.52.5 fix restores the pre-0.39
abort-on-first-transient-read behaviour for the bounded scan paths only
(`read(..., retry_transient=False)` in `scan_module` / `scan_matches`);
one-shot reads (patch verification, pointer chains, write readback) keep
the 0.39 retry unchanged.

## What this proves and what it cannot prove

Proves: for this table, the *content and order* of every read, scan,
write, allocation, protection and restore the trainer performs is
unchanged between 0.33 and current main. A crash caused by the trainer
*writing different bytes, to different addresses, in a different order*
is ruled out across the whole crash window.

Cannot prove: the transient-read behaviour itself is invisible to the
replay (the synthetic memory never fails transiently, so the
call-count delta — 1 vs up to 4 kernel reads per chunk — only exists on a
real transient Win32 299). The field crash shape (steady-state idle,
last event `patch-verify-skipped` (Win32 299) ~260 ms before
`target-exited`, zero writes in both sessions) plus the widened 0.52.5
scan forensics (`rearm-scan-start`, `scan_transient_abort`,
`bytes_scanned`) are the field-side confirmation; the WER dumps and the
0.31-vs-0.52.5 A/B run are the requested closing evidence.

## Inputs

- Table (local-only, not distributable, referenced by sha256):
  `TheGreatCircle_Plus21_extracted.ct`
  `4e0dc0b54a5d96526d680042fe323bcfc4421327559c201f0b688279fff18c2b`
  (46 entries, pure Auto Assembler, process `TheGreatCircle.exe`).
- Same synthetic module image and fixed identity (PID 424242, creation
  time 134399935579190145, pointer size 8) as the 0.52.4 replay
  (`PLACEMENTS` in `gc_replay.py`); `aobhealth2` / `aobammo2`
  deliberately absent → ScanMiss, as observed in the field.
- Trees: 0.33 = `main` @ `6e71739` (worktree `side/wt-033`);
  0.41 = `main` @ `c724a7e`; main = the 0.52.5 pre-fix checkout.

## Regenerating

```
set CT2TRAINER_NASM=<repo>\.tools\native\nasm-3.02\nasm-3.02\nasm.exe
python gc_replay.py <tree_at_6e71739> <table.ct> out-033.json
python gc_replay_diff_norm.py out-033.json replay-041.json > diff-norm-033-041.txt
python gc_replay_diff_norm.py out-033.json replay-main.json > diff-norm-033-main.txt
```

`replay-041.json` / `replay-main.json` live in
`documentation/evidence/gc-0524-replay/`. The harness is self-contained
apart from the tree-under-test's `src/` (pinned NASM required) and the
local table file.

## Artifacts

| file | content |
|------|---------|
| `gc_replay.py` | deterministic replay harness (parameterized) |
| `gc_replay_diff_norm.py` | deep diff with traceback normalization (path/line-number artifact of the by-design ScanMiss wishes) |
| `replay-033.json` | replay at 0.33 (`main` @ `6e71739`) |
| `diff-norm-033-041.txt` | 0.33 vs 0.41 comparison, `TOTAL DIFFERENCES: 0` |
| `diff-norm-033-main.txt` | 0.33 vs main comparison, `TOTAL DIFFERENCES: 0` |
| `plan-diff-041-main.txt` | plan-shape diff 0.41 (== 0.33) vs main: only the 15 empty `unowned_cleanup_dropped: []` fields |
| `window-033-main-filestat.txt` | `git diff --stat` of the 0.33→main window (46 files) |
| `diff-033-043-coord.txt` | 0.33→0.43 `hooks.py` / `debug_coordinator.py` diff (transient re-raise, failure path only) |
| `diff-043-0523-coord.txt` | 0.43→0.52.3 `hooks.py` / `debug_coordinator.py` diff (direction-aware prefix-cut close validation, validation path only) |
