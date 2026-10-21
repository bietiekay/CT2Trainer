# CT2Trainer — Central Gap & Goal Tracking

For a concise explanation of these measurements and the overall goal,
see [Current status](../STATUS.md). Update it with this tracker whenever
new evidence changes a count, gate, build or next step.

## Current decision (2026-10-20)

The active objective is [100% support of the local reference tables](reference-table-100-roadmap.md).
The 0.16 Wave-4 package set is complete. The 42/42 feature matrix proves
coverage of the 30 pinned **synthetic** cases, not the 151 original-table
paths (143 distinct hashes). The latest local-only original-table catalog
has 2,698 blocked of 117,624 plan entries and one legacy-binary load
error. The figures below describing earlier waves and old `ready` package
states are historical baselines; use the goals and queue immediately below
for active work. No original table contents enter the repository.

### Active goals

| ID | Outcome | State | Exit evidence |
| --- | --- | --- | --- |
| GOAL-8 | 100% reference-table load and semantic support | open | RT-1 through RT-5 in the roadmap; all 151 paths/143 distinct hashes inventoried, all intended actions executable, no unexplained blocked or staged rows, no hidden table-level construct. |
| GOAL-9 | 100% original-table observed behavior | open | RT-6; per-table game-build/runtime evidence for distinct behavior contracts. Unavailable game targets remain explicitly unverified. |
| GOAL-10 | Clean Windows and Steam Deck acceptance | open | Both platform protocols recorded with exact build, hashes, setup and result; only then reassess `runtime_unverified`. |
| GOAL-11 | Clean-room redistributable release | active guard | RT-7; independent implementation, no CE code/binaries/original tables in shipped ZIPs, offline build proof. |

GOAL-1 is complete only for the synthetic feature matrix; GOAL-2 remains
open and its old 85% estimate is superseded by the 100% reference-table
target. GOAL-3/AP-11 (0/6,143 confirmed) is a separate game campaign.
GOAL-4/5/6 remain open; GOAL-7 is historical release work.

### First packages

| Package | Owner | State | Next concrete output |
| --- | --- | --- | --- |
| RT-1 full-corpus rebaseline | root | done (2026-10-21) | Frozen manifest `gap_inventory/reference-manifest.json` (151 paths, 143 hashes, exact EXE bindings); catalog re-run on the 0.16 source (`blocked-catalog-rt1`) identical per table to the 2026-10-20 run (2,698 / 117,624, 1 legacy-binary load error); stale 15/27-table prose in `gap-report.json`/`feature-coverage.json` repaired at the tool source and regenerated under the pinned run id. |
| RT-2 residual attribution | root | done (2026-10-21) | All 2,698 blocked rows traced to an upstream terminal cause (lane final2 run; root re-verified every class sum and per-table sum in both directions and independently re-ran the corrected UNDEFINED-split logic against the local corpus): 1,931 cascade rows = 1,304 undefined-symbol (963 AA-hidden in-table registrations, 110 Lua-runtime, 91 no-registration, 128 legacy built-in, 12 API export) + 624 duplicate-provider cascades + 3 wildcard-cleanup; 767 direct rows in 27 classes. Per-class testable contract, risk, expected delta and the RT-4 package split (P1 814 / P2 963 / P3 203 / P4 341 / P5 140 / P6 122 / P7 43 / P8 64 / documented refusals 8; sums to 2,698) recorded in the roadmap's RT-2 root-cause map; CE 7.5 behavior probes (dropdown overflow truncates, module names stored with .exe, IL2CPP Type:Member pipe-server-only) recorded with source citations. |
| RT-3 legacy binary load | unassigned | design | Determine independently implementable format contract and table-level completeness test. |
| RT-4 high-volume semantics | unassigned | design | Addressless ancestor, provider cascades, offsets, duplicate provider and AA residuals. |
| RT-5 runtime trainer parity | unassigned | design | Usage census, bounded game-facing host contracts and owned-target proofs; visual CE UI is outside scope. |

No active worker is implied by `ready` or `design`. WP-19…58 below are
completed historical waves except WP-42; its embedded Forms rendering is
outside the requested visual UI scope unless a form control mediates a
game-facing action.

## Current measurement

- Synthetic pinned corpus: 30 tables, 6,143 expected AP-11 actions; feature
  matrix 42/42 and action weight 7,475/7,475 (run
  `w4b4-case30-20261020081722Z`). This does not measure original-table
  parity.
- Local original reference catalog: 151 paths, 143 distinct hashes,
  114,926 supported (58,950 staged) and 2,698 blocked of 117,624 plan
  entries; one legacy-binary load error (post-Wave-4 catalog, 2026-10-20;
  RT-1 re-run on the 0.16 source, 2026-10-21, reproduces all counts per
  table — frozen manifest `gap_inventory/reference-manifest.json`).
- AP-11 confirmed effects: 0/6,143. Windows and real Deck acceptance
  remain open; `runtime_unverified` remains set.
- Latest verified release: 0.16.1, build
  `native-20261021T161241Z-b0566a25` (cut from `main` @ `d1c61f2`),
  in-build suite 3,412 OK / 25 expected skips, `ce_inputs: []`;
  superseded 0.16 field-fix re-cut 2
  `native-20261021T123801Z-8c5c4e1e` (in-build 3,405/25, user-tested,
  field finding: Sinking City 2 table-load warnings) and re-cut
  `native-20261020T150115Z-c426fb92` (in-build 3,398/25, user-tested,
  field findings: one cheat = table/build mismatch, state-lock orphan
  after a blocked close).
- 0.16 field-fix round 2 (2026-10-21, branch `native-0.16-lock-selfheal`):
  state-lock self-repair and reliable restart — close() completes when
  blocked and the target is gone (lock/session released, wishes kept),
  atexit session/lock release on a provably gone target, actionable
  stale-lock refusal with assessment reasons and one probe retry; 7 new
  regression tests, local suite 3,405 OK / 25 expected skips. Built as
  `native-20261021T123801Z-8c5c4e1e` (in-build 3,405/25, `ce_inputs:
  []`); the field finding "Inf Items" is a table/build mismatch (no
  code change).
- 0.16.1 field-fix round (2026-10-21, branch `native-0.16.1-sc2-warnings`):
  Sinking City 2 table-load warnings made accurate — table-version
  reference 45 → 46 (CE 7.5 writes 45; v46 field-verified, 13 of the 30
  pinned tables are v46), `{$LUA}` warning now states the built-in Lua
  runtime path, external-action warning split per API (ShellExecute =
  documented safe no-op, messageDialog = real review flag);
  `tests/test_native_sc2_table_warnings.py` (7 tests) + version
  assertion moved to reference 46. Versioning rule (user decision):
  every build gets a new version number, bug fixes bump the patch —
  VERSION 0.16 → 0.16.1 (first build under the rule). Built as
  `native-20261021T161241Z-b0566a25` (in-build 3,412/25, `ce_inputs:
  []`).

## Historical evidence

- [Archived goal and integration ledger](archive/TRACKING-history.md) —
  Wave 1–4 gap tables, case registry, work-package decisions and merge log.
- [Archived plans](archive/README.md) — completed AP/WP designs.
- [Progress ledger](../documentation/native-progress.md) — build and
  acceptance evidence.
- [CE trainer-behavior assessment](../documentation/ce-feature-parity-assessment.md)
  — capability map and full-corpus method.
