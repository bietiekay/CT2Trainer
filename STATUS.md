# CT2Trainer: where we stand

**Updated:** 2026-10-26. **Latest verified release:** 0.16.4, build
`native-20261024T003853Z-a8cf04fc` (built from `main` at `988ff8e`,
2026-10-24): the Sinking City 2 trainer-crash-observability field fix
(from the 0.16.3 field test: the windowed trainer process died
silently mid wish-restore with zero follow-up log events and the
restart was blocked by the correct state-lock refusal while the game
was alive; `arm_crash_reporting()` now sinks
excepthook/threading-hook/faulthandler evidence into the opt-in debug
log, `TrainerWindow.poll` fails closed instead of letting an exception
kill the windowed process, and the restore loop logs
`restore-entry-start` per wish; state-lock fail-closed behavior
unchanged) on top of the 0.16.3 content, the RT-4.4 value-semantics,
the RT-4.6 input-legacy and the RT-4.5 AA-directive merges (catalog
remeasure `blocked-catalog-rt45main`: 1,743 blocked of 117,634, zero
newly blocked rows); `main` since the 0.16.4 cut additionally carries
the RT-4.3 address-expression & identifier-dialect merge (2026-10-26,
merge `cd3217d`): O1 relative-address skip-fold + O9 runtime-base
staging, O3 pointer-offset expression slots, O10 identifier dialect,
O23 token-named quoted-atom refusal, O27/O4 Type:Member managed
labels, O13 directive-aware db/dw/dd/dq string bytes — catalog
remeasure `blocked-catalog-rt43-main`: 1,743 -> 1,351 blocked of
117,634, zero newly blocked rows; plus the RT-5 item G
createThread/threadWait gate decision (2026-10-26, merge `2de9c0e`):
option (2) recorded — capability gate stays, no thread backend ships
this milestone, byte-stable five-stage gate pins
`tests/test_native_rt5_thread_gate.py` +17, tests only, zero catalog
movement (`blocked-catalog-rt5g-main` zero delta). The 0.17 build is cut
after the remaining RT-4.2 merge (1,085).
Superseded: 0.16.3, build
`native-20261023T065015Z-afbc3eba` (built from `main` at `6a5ba63`,
2026-10-23) - the Sinking City 2 activation field fix (two root
causes from the 0.16.2 field test: the recovery assessment still
rejected the WP-47/55 hook-journal `value_data_ranges` field on
every allocation entry, blocking startup behind a stale
`state.lock` on every attempt; and the module-snapshot retry
targeted the wrong Win32 code without backoff, so the transient
failure while the game was still loading DLLs was never retried -
now a bounded 8-attempt exponential-backoff retry on {1116, 24, 119}
with the architecture-aware fallback flag and the journal field
validated with the writer contract) on top of the 0.16.2 content;
user-tested, field finding: the 0.16.3 Sinking City 2 field test
found the silent mid-restore death above (ledger). Superseded:
0.16.2, build
`native-20261022T160328Z-0423fb21` (built from `main` at `68eeb00`,
2026-10-22) - the Sinking City 2 startup-block field fix (recovery
assessment accepts the WP-57 hook-journal `captured_placeholders`
field, which had blocked recovery behind a stale `state.lock`) plus
RT-4.1 symbol provider fidelity (keep-first duplicate-provider
policy, `label()` duplicate-name tolerance, wildcard-cleanup
scoping, catalog remeasure 2,698 -> 1,858 blocked of 117,624, zero
unexplained supported regressions); user-tested, field finding: the
0.16.2 Sinking City 2 field test found the activation failure above
(ledger). Superseded:
0.16.1, build
`native-20261021T161241Z-b0566a25` (built from `main` at `d1c61f2`,
2026-10-21) - Sinking City 2 table-load warnings made accurate + new
versioning rule (every build gets a new version number, bug fixes bump
the patch); user-tested, field finding: the 0.16.1 Sinking City 2
field test found the startup block above (ledger).
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
| Independently built product | 0.16.4 source and Windows portable ZIPs passed the offline build with **3,479 tests OK, 25 expected skips**, and `ce_inputs: []`. | Keep the clean-room build and release checks green after each change. |
| Synthetic feature coverage | **42/42** declared feature classes and **7,475/7,475** action weight covered across **30 synthetic tables**. | This metric does not establish support for every original table or a real game effect. Add synthetic cases when a new behavior is found. |
| Original reference tables | All **151/151** table paths load after the RT-3 legacy-binary CT loader (2026-10-23). Local static catalog (RT-4.3 remeasure, run `blocked-catalog-rt43-main`, 2026-10-26, frozen manifest `gap_inventory/reference-manifest.json`) classifies **116,283 supported**, including **59,868 staged**, out of **117,634 plan entries**. | **1,351 entries are blocked** (was 2,698 before RT-4.1, 1,858 after RT-4.1/RT-3, 1,807 after RT-4.4, 1,778 after RT-4.6, 1,743 after RT-4.5; RT-4.3 cleared 392 rows — O1 relative-address skip-fold 195, O3 pointer-offset expression slots 51, O4/O27 atoms 38, O9 runtime-base staging 8, O13 indirect data 5, O10 direct 5 plus 90 dependent provider-lookup rows — with zero newly blocked rows and 12 reason-only changes). Staged entries still need their runtime conditions proved. |
| Observed game effects | Owned fixtures and selected runtime chains have tests. | The AP-11 campaign has **0 of 6,143** game effects confirmed. Original-table behavior must be checked against pinned game builds or explicitly equivalent owned targets. |
| Final platforms | The 0.9.0-rc2 portable converter and a generated trainer were user-tested without CE or Python; later fixture tests cover many runtime paths. The 0.16 re-cut was field-tested 2026-10-21 (new WP-58 UI confirmed good; one cheat = table/build mismatch, no fix; the state-lock orphan after a blocked close was fixed in code the same day, see the ledger). The Sinking City 2 table-load warnings were made accurate in 0.16.1 (2026-10-21): table-version reference 45 → 46 field-verified, `{$LUA}`/`ShellExecute` wording now states the supported native behavior — the table itself loaded fine (see the ledger). The 0.16.1 field test (2026-10-21, Sinking City 2) exposed a startup block behind a stale `state.lock`: WP-57 hook journals with `captured_placeholders` failed the recovery schema; fixed on `main` 2026-10-22 (0.16.2, built as `native-20261022T160328Z-0423fb21` — see the ledger). The 0.16.2 field test (2026-10-22, Sinking City 2) exposed the next activation failure: the startup brick from the still-missing journal field `value_data_ranges` plus a module-snapshot retry aimed at the wrong Win32 code (mislabeled 24 instead of 1116) without backoff while the game was still loading DLLs (field log: Win32 error 24 nine ms after attach); both root causes fixed on `main` 2026-10-23, shipped as 0.16.3 (see the ledger). | The 0.16 re-cut has no recorded full clean-machine acceptance. Clean Windows and real Steam Deck/Proton/touch acceptance remain open. `runtime_unverified` stays set. |

**The 42/42 result is real, but it measures the synthetic feature matrix.**
The 1,351 blocked entries (after the RT-4.3 remeasure, was 1,743 after
RT-4.5, 1,778 after RT-4.6, 1,807 after RT-4.4, 1,858 after
RT-4.1/RT-3 and 2,698 at the Wave-4 baseline), staged
runtime behavior, and absent game-effect evidence are why the overall
100% reference-table goal is still open.
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
3. **Implement the missing behavior (RT-3 to RT-5; RT-3, RT-4.1,
   RT-4.4, RT-4.6 and RT-4.5 done):** RT-3 legacy-binary CT loading
   landed 2026-10-23 (clean-room parser, `SuperMeatBoy.CT` 10/10
   supported, table load 151/151); RT-4.4 value semantics landed
   2026-10-23 (catalog remeasure `blocked-catalog-rt44`: 1,858 ->
   1,807 blocked, 51 value-semantics rows cleared, zero newly
   blocked); RT-4.6 input legacy & authoring gaps landed 2026-10-24
   (catalog remeasure `blocked-catalog-rt46`: 1,807 -> 1,778 blocked,
   29 rows cleared, zero newly blocked, 218 reason-only changes onto
   the actionable per-symbol report); RT-4.5 AA directive & script
   coverage landed 2026-10-24 (catalog remeasure
   `blocked-catalog-rt45main`: 1,778 -> 1,743 blocked, 35 rows
   cleared, zero newly blocked, 7 reason-only changes); RT-4.3 address
   expression & identifier dialect landed 2026-10-26 (catalog remeasure
   `blocked-catalog-rt43-main`: 1,743 -> 1,351 blocked, 392 rows
   cleared, zero newly blocked, 12 reason-only changes; dedicated
   dialect tests now at 38). The RT-5 API/construct inventory is
   documented in `documentation/rt5-api-inventory.md`; RT-5 item G
   (createThread/threadWait gate decision, option 2 — gate stays, no
   thread backend this milestone) landed 2026-10-26, tests-only, zero
   catalog movement. Remaining: RT-4.2 runtime provider model (1,085;
   last RT-4 package), then the RT-5 implementation items A-F.
4. **Trainer UI feature (user request, done 2026-10-24):** the
   `Scripts` filter view (every script record, blocked/unselected
   included with their reason; headings and values hidden) and the row
   context menu (right-click / long-press) with script preview (the
   executed Auto Assembler / Lua source), copy-script, plain-language
   entry assessment and the unchanged Info dialog — merged on branch
   `native-0.17-ui-script-inspector` (suite 3,587 OK / 25 expected
   skips; catalog remeasure `blocked-catalog-ui-scripts` zero delta).
   Ships in the 0.17 build cut after the remaining RT-4.x merges
   (user decision 2026-10-24).
5. **Verify original effects and platforms (RT-6):** record activation,
   values, freeze, re-attach, disable/undo and one-shot behavior where
   applicable. Run the Windows and Deck protocols with exact build
   hashes and setups.
6. **Release only with evidence (RT-7):** full suite, offline build,
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
