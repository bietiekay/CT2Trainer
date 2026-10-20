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
| RT-1 full-corpus rebaseline | root | ready | Freeze 151 path/143-hash manifest and process bindings, rerun on 0.16 source, reconcile entry totals and errors; repair stale 15/27-table prose fields in `gap-report.json`. |
| RT-2 residual attribution | root | ready | Group all 2,698 blocked rows by upstream cause, inspect leading tables, assign code packages after synthetic cases. |
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
  entries; one legacy-binary load error (post-Wave-4 catalog, 2026-10-20).
- AP-11 confirmed effects: 0/6,143. Windows and real Deck acceptance
  remain open; `runtime_unverified` remains set.
- Latest verified release: 0.16 field-fix re-cut, build
  `native-20261020T150115Z-c426fb92`, in-build suite 3,398 OK / 25
  expected skips, `ce_inputs: []`.

## Historical evidence

- [Archived goal and integration ledger](archive/TRACKING-history.md) —
  Wave 1–4 gap tables, case registry, work-package decisions and merge log.
- [Archived plans](archive/README.md) — completed AP/WP designs.
- [Progress ledger](../documentation/native-progress.md) — build and
  acceptance evidence.
- [CE trainer-behavior assessment](../documentation/ce-feature-parity-assessment.md)
  — capability map and full-corpus method.
