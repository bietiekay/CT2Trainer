# CT2Trainer: where we stand

**Updated:** 2026-10-20. **Latest verified release:** 0.16 field-fix
re-cut, build `native-20261020T150115Z-c426fb92` (built from `main` at
`7616edb`). This page is a short explanation of the evidence in
[central tracking](plans/TRACKING.md) and the
[progress ledger](documentation/native-progress.md).

## The goal

Support the intended **trainer and cheat behavior** of all 151 local
reference-table paths (143 distinct file hashes), without copying Cheat
Engine code, binaries or original table content into CT2Trainer. CE editor
and visual UI features are outside scope unless a table uses them to
cause a game effect. The [roadmap](plans/reference-table-100-roadmap.md)
defines the work and completion gates.

## Achievement and remaining work

| Area | Achieved | Still needed |
| --- | --- | --- |
| Independently built product | 0.16 source and Windows portable ZIPs passed the offline build with **3,398 tests OK, 25 expected skips**, and `ce_inputs: []`. | Keep the clean-room build and release checks green after each change. |
| Synthetic feature coverage | **42/42** declared feature classes and **7,475/7,475** action weight covered across **30 synthetic tables**. | This metric does not establish support for every original table or a real game effect. Add synthetic cases when a new behavior is found. |
| Original reference tables | The latest local static catalog classifies **114,926 supported**, including **58,950 staged**, out of **117,624 plan entries**. | **2,698 entries are blocked** and one legacy-binary table does not load. Staged entries still need their runtime conditions proved. Re-run the catalog on a frozen input/process manifest. |
| Observed game effects | Owned fixtures and selected runtime chains have tests. | The AP-11 campaign has **0 of 6,143** game effects confirmed. Original-table behavior must be checked against pinned game builds or explicitly equivalent owned targets. |
| Final platforms | The 0.9.0-rc2 portable converter and a generated trainer were user-tested without CE or Python; later fixture tests cover many runtime paths. | The fixed 0.16 re-cut has no recorded full clean-machine acceptance. Clean Windows and real Steam Deck/Proton/touch acceptance remain open. `runtime_unverified` stays set. |

**The 42/42 result is real, but it measures the synthetic feature matrix.**
The 2,698 blocked entries, staged runtime behavior, and absent game-effect
evidence are why the overall 100% reference-table goal is still open.
"Supported" in the static catalog means plan admission, not confirmed
effect in a game.

**Measurement caveat:** the committed `gap-report.json` has the current
structured totals (30 tables, 6,143 actions) but still contains stale
prose fields naming older 15/27-table baselines. RT-1 must reconcile or
regenerate those fields before using them as current guidance.

## What happens next

1. **Reproduce the full-corpus baseline (RT-1):** lock the 151 paths,
   hashes and exact target EXE names; rerun the catalog against the
   current source and reconcile counts.
2. **Explain every remaining block (RT-2):** trace provider cascades to
   their root cause. Current leading reasons include the `Esau_base`
   provider, addressless-ancestor relative addresses and pointer offsets.
3. **Implement the missing behavior (RT-3 to RT-5):** handle the legacy
   binary table and the proven address, AA, Lua and runtime gaps with
   independently authored synthetic cases and owned-target tests.
4. **Verify original effects and platforms (RT-6):** record activation,
   values, freeze, re-attach, disable/undo and one-shot behavior where
   applicable. Run the Windows and Deck protocols with exact build
   hashes and setups.
5. **Release only with evidence (RT-7):** full suite, offline build,
   source/frozen parity, `ce_inputs: []`, and updated tracking and
   verification records.

The current capability map is in the
[CE trainer-behavior assessment](documentation/ce-feature-parity-assessment.md).
Completed AP/WP plans are in [the archive](plans/archive/README.md).

## How this page is maintained

This page summarizes evidence; [TRACKING.md](plans/TRACKING.md) owns the
active goals and detailed counts. Update this page **in the same change**
whenever a work package changes the full-corpus catalog, a synthetic case
or feature-matrix result changes, a game-effect or platform observation is
recorded, or a release/build status changes. State the observation date,
build or source revision, input/run identifier and denominator. Keep
synthetic coverage, original-table static coverage and observed effects
separate. If evidence is missing or a measurement is stale, say so; do
not silently carry a prior percentage forward.
