# CT2Trainer: where we stand

**Updated:** 2026-10-22. **Latest verified release:** 0.16.1, build
`native-20261021T161241Z-b0566a25` (built from `main` at `d1c61f2`);
Sinking City 2 table-load warnings made accurate + new versioning rule
(every build gets a new version number, bug fixes bump the patch) built
2026-10-21. On `main` 2026-10-22: RT-4.1 symbol provider fidelity
(keep-first duplicate-provider policy, `label()` duplicate-name
tolerance, wildcard-cleanup scoping — catalog remeasure 2,698 -> 1,858
blocked of 117,624, zero unexplained supported regressions) and the
0.16.2 field fix (build pending): the 0.16.1 Sinking City 2 field test
found a startup block — WP-57 hook-journal `captured_placeholders`
were rejected by the recovery assessment, so placeholder-capture
journals blocked recovery behind a stale `state.lock`; the field is now
validated and accepted (ledger).
This page is a short explanation of the
evidence in
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
| Independently built product | 0.16.1 source and Windows portable ZIPs passed the offline build with **3,412 tests OK, 25 expected skips**, and `ce_inputs: []`. | Keep the clean-room build and release checks green after each change. |
| Synthetic feature coverage | **42/42** declared feature classes and **7,475/7,475** action weight covered across **30 synthetic tables**. | This metric does not establish support for every original table or a real game effect. Add synthetic cases when a new behavior is found. |
| Original reference tables | Local static catalog (RT-4.1 remeasure 2026-10-22, run `blocked-catalog-rt41`, frozen manifest `gap_inventory/reference-manifest.json`) classifies **115,766 supported**, including **59,642 staged**, out of **117,624 plan entries**. | **1,858 entries are blocked** (was 2,698 before RT-4.1) and one legacy-binary table does not load. Staged entries still need their runtime conditions proved. |
| Observed game effects | Owned fixtures and selected runtime chains have tests. | The AP-11 campaign has **0 of 6,143** game effects confirmed. Original-table behavior must be checked against pinned game builds or explicitly equivalent owned targets. |
| Final platforms | The 0.9.0-rc2 portable converter and a generated trainer were user-tested without CE or Python; later fixture tests cover many runtime paths. The 0.16 re-cut was field-tested 2026-10-21 (new WP-58 UI confirmed good; one cheat = table/build mismatch, no fix; the state-lock orphan after a blocked close was fixed in code the same day, see the ledger). The Sinking City 2 table-load warnings were made accurate in 0.16.1 (2026-10-21): table-version reference 45 → 46 field-verified, `{$LUA}`/`ShellExecute` wording now states the supported native behavior — the table itself loaded fine (see the ledger). The 0.16.1 field test (2026-10-21, Sinking City 2) exposed a startup block behind a stale `state.lock`: WP-57 hook journals with `captured_placeholders` failed the recovery schema; fixed on `main` 2026-10-22 (0.16.2, build pending — see the ledger). | The 0.16 re-cut has no recorded full clean-machine acceptance. Clean Windows and real Steam Deck/Proton/touch acceptance remain open. `runtime_unverified` stays set. |

**The 42/42 result is real, but it measures the synthetic feature matrix.**
The 2,698 blocked entries, staged runtime behavior, and absent game-effect
evidence are why the overall 100% reference-table goal is still open.
"Supported" in the static catalog means plan admission, not confirmed
effect in a game.

**Measurement note:** the committed `gap-report.json` carries the
current structured totals (30 tables, 6,143 actions); the stale
15/27-table prose fields were repaired in the RT-1 rebaseline
(2026-10-21) at the tool source, with the committed artifacts
regenerated under the pinned run id
`w4b4-case30-20261020081722Z`.

## What happens next

1. **Full-corpus baseline (RT-1, done 2026-10-21):** 151 paths /
   143 hashes frozen in `gap_inventory/reference-manifest.json` with
   exact EXE bindings; the catalog re-run on the 0.16 source reproduces
   the 2026-10-20 counts exactly (2,698 / 117,624, 1 legacy-binary load
   error).
2. **Explain every remaining block (RT-2, done 2026-10-21):** all 2,698
   blocked rows traced to terminal causes - 1,931 cascade rows (963
   hidden in-table registrations, 110 Lua-runtime symbols, 91
   no-registration triage, 128 legacy built-ins, 12 API exports, 624
   duplicate-provider cascades, 3 wildcard-cleanup conflicts) and 767
   direct rows in 27 classes; per-class contracts, risks, expected
   deltas and the RT-4 package split (RT-4.1…RT-4.6, sums to
   2,698) are in the roadmap's RT-2 root-cause map (lane final
   report, 2026-10-21 21:14, authoritative record).
3. **Implement the missing behavior (RT-3 to RT-5; RT-4.1 done
   2026-10-22):** handle the legacy binary table and the remaining
   address, AA, Lua and runtime gaps with independently authored
   synthetic cases and owned-target tests. RT-4.1 symbol provider
   fidelity landed first (catalog 2,698 -> 1,858 blocked, net -840);
   next package: RT-4.3 address expression & identifier dialect (452).
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
