# CT2Trainer: where we stand

**Updated:** 2026-10-31. **Latest verified release:** 0.20.1, build
`native-20261031T104114Z-d64ae4c2` (built from `main` at `080128c`,
2026-10-31): the 0.20.1 release-content re-cut of the 0.20 branding-icon
release - the 0.20 changelog suite line now states the verified in-build
suite (3,854 OK / 26 expected skips, fully green at the canonical build
path) and cites catalog remeasure `blocked-catalog-020-icons` (zero delta
vs `blocked-catalog-019-field`); no code or asset changes; in-build suite
3,854 OK / 26 expected skips, `ce_inputs: []`, `runtime_unverified`
deliberately kept per gate. Superseded 0.20, build
`native-20261030T184820Z-b9d6dc07` (built from `main` at `6298803`,
2026-10-30): the branding-icon release - the user-provided
`CT2Trainer_Generator` icon set for the CT2Trainer tool (embedded in the
frozen `CT2Trainer-Converter.exe` via PyInstaller `--icon`; converter
window via `window_icon_path("converter")`) and the `Standalone_Trainer`
icon set embedded in the `CT2Trainer-Template` stub so every generated
trainer .exe carries it (trainer window via `window_icon_path("trainer")`);
1024x1024 PNG masters committed as reference, multi-size ICOs (16-256 px,
32 bpp) rebuilt by the rewritten `tools/create_icons.py` (Pillow is
local-only, outside the offline wheels), `tests/test_native_icons.py` +4;
suite 3,854 OK / 26 expected skips, zero catalog delta vs
`blocked-catalog-019-field` (151/117,634/60,161/1,053/0 load errors),
`ce_inputs: []`, `runtime_unverified` deliberately kept per gate (the
first 0.20 cut, `native-20261030T183527Z-8f2cb20a`, was cut from the
wrong branch - duplicate 0.19 ZIPs without icons - and deleted before
recording). Superseded 0.19, build
`native-20261030T121918Z-c72dbb38` (built from `main` at `fbe626f`,
2026-10-30): the 0.19 field-fix cycle - hotkey-bridge Windows AV fix
(HWND_MESSAGE corrected to -3; explicit Win32 argtypes/restype on all
bridge prototypes; RegisterHotKeyW/UnregisterHotKeyW guarded for
stripped user32 builds; +1 real-seam regression test), value-read
observability (`read_value` logs `value-read-failed` per identifier
per cause, dedup, re-raise), the new `describe` CLI subcommand (raw
source + plain-language assessment + concrete trainer actions per
record, +13 tests), and full staged-options support for the South of
Midnight table (plan-level staging, engine gates and the two-level
parent cascade proven correct by new tests; UI gaps closed:
staged-pending value rows now refuse immediately in the status line
with the engine's named provider refusal, and `moAlwaysHideChildren`
passes through as the `hidden_children` plan marker with row-model
subtree suppression - the flagged parent row stays the interface);
+24 tests, suite 3,850 OK / 26 expected skips, zero catalog delta vs
`blocked-catalog-rt5d-main` (151/117,634/60,161/1,053/0 load errors),
`ce_inputs: []`, `runtime_unverified` deliberately kept per gate.
Superseded 0.18, build
`native-20261028T131208Z-55922918` (built from `main` at `70c5a61`,
2026-10-28): the trainer UI row-details window - right-click /
long-press on a row now offers "Row details" leading the context menu,
a single read-only window combining the raw script source (static Auto
Assembler / embedded Lua / global program / normalized operation list),
the plain-language assessment (what it does / what is known) and the
concrete actions the trainer performs for the entry (new pure builders
`entry_actions` / `row_details` / `lua_apis_used` in
`ui_script_view.py`, +22 tests in
`tests/test_native_ui_row_details.py`); in-build suite 3,767 OK / 25
expected skips, `ce_inputs: []`, `runtime_unverified` deliberately kept
per gate. Superseded: 0.17, build
`native-20261027T094839Z-ec6c6f55` (built from `main` at `ee41630`,
2026-10-27): the RT-4.2 runtime provider model (last RT-4 package;
catalog remeasure `blocked-catalog-rt42-main`: 1,351 -> 1,053
blocked, 298 rows unblocked, zero newly blocked, 28 reason-only
changes) on top of the 0.16.4 content, the RT-4.3
address-expression & identifier-dialect merge (2026-10-26,
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
movement (`blocked-catalog-rt5g-main` zero delta); plus the RT-5 item F
no-effect register ratification (2026-10-26, merge `966fccd`,
tests-only: the inventory section-8 no-effect/out-of-scope register
pinned as a byte-stable contract,
`tests/test_native_rt5_no_effect_register.py` +22, zero catalog
movement, `blocked-catalog-rt5f-main` zero delta); plus the RT-5 item A
embedded `<Files>` extraction & Lua surface (2026-10-28, merge `479977c`):
new `src/ct2trainer/native/embedded_files.py` dual-branch codec (CE-alphabet
Ascii85 + 4-byte-LE size prefix; hex read-until-EOF for other/missing
`Encoding`), fail-closed table-load decode, `findTableFile`/`readStringLocal`/
stringstream/stringlist surface, +53 tests; zero catalog delta
(`blocked-catalog-rt5a-main`), full main suite 3,745 OK / 25 expected
skips; plus the RT-5 item C bounded process-info Lua API family
(2026-10-28, commit `0167825`): 11 CE 7.5 process-info APIs under the
clean-room single-target model (getProcessIDFromProcessName,
getProcessList, getAutoAttachList, getOpenedProcessID, getSettings,
integerToUserData, targetIs64Bit, enumModules, disassemble,
stringlist_add, getCEVersion pinned '7.5'), item-A-style allowlist
wiring, +23 tests; zero catalog delta (`blocked-catalog-rt5c-main`), full
main suite 3,790 OK / 25 expected skips; plus the RT-5 item C2 dynamic
addresslist records + custom AA directives (2026-10-29, merge
`dde9f04`): createMemoryRecord session journal (IDs >= 2**31, never
persisted, cleared on target exit), CE MemoryRecord runtime surface
(Description/Type/Address/Script/Parent/Child/Offset/OffsetText/Value
vtByte..vtDouble), journal + plan OnActivate/OnDeactivate callbacks,
getCEVersion number 7.5 (item-C string pin superseded), addresslist
getMemoryRecord/Count/MemoryRecord[i] lookups,
registerAutoAssemblerCommand custom AA directives (table scope, built-in
names refused), `tests/test_native_rt5_dynamic_records.py` +27; zero
catalog delta (`blocked-catalog-rt5c2-main`), full main suite 3,817 OK /
25 expected skips; plus the RT-5 item D onOpenProcess/onTableLoad
callback dispatch (2026-10-29, merge `9294bb8`): CE-sequence
table-scope dispatch after a clean table-Lua bootstrap (onOpenProcess
with the attached target PID, onTableLoad with the Lua literal false -
documented bounded deviation: no before-load phase), pcall-wrapped
dispatch chunks with literal argument injection, 'absent'/'ok'/
'error: <msg>' -> no event / table-callback / table-callback-error,
throwing-callback containment with plan byte-identity, idempotent per
confirmed attach with re-attach re-fire,
`tests/test_native_rt5_table_callbacks.py` +9; zero catalog delta
(`blocked-catalog-rt5d-main`), full main suite 3,826 OK / 25 expected
skips. RT-4 is complete; RT-5 items A, C, C2 and D are the
first implementation items landed. The 0.17 in-build suite:
3,692 OK / 25 expected skips, `ce_inputs: []`.
Superseded: 0.16.4, build
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
newly blocked rows). Superseded: 0.16.3, build
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

**0.21 Master Trainer feature work (2026-10-31, branch
`native-0.20-master-trainer`, merged `main` @ `322ae22`; build cut
from the canonical path after the merge):** one long-lived trainer
window configured with a folder of `.ct` tables — incremental,
checksum-bound table index (folder + sub-folders; only the folder is
listed per reconcile, changed files re-read), cross-platform process
watch (Toolhelp32 on Windows, `/proc/<pid>/exe` on Linux/SteamOS),
auto-load of the unique matching table, table picker when several bind
one process, switch into the exact standalone `TrainerWindow` with a
`master_back` button, per-table on/off persistence via the existing
engine state store, pure UI-free orchestrator, `ct2trainer native
master` CLI and the user-provided `Master_Trainer` icon
(`window_icon_path("master")`). 141 new tests plus the three-kind icon
contract; four source bugs found and fixed during test-lane
development. Dev suite on the merged branch: 4,011 OK / 30 expected
skips of 4,044 (only the 3 known worktree path-dependent
baseline-reproducibility tests fail; they pass at the canonical build
path); catalog unchanged vs `blocked-catalog-020-icons`.

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
| Independently built product | The 0.20.1 source and Windows portable ZIPs passed the offline build (build `native-20261031T104114Z-d64ae4c2`) with **3,854 tests OK, 26 expected skips**, and `ce_inputs: []`; the user-provided branding icons are embedded in the frozen converter EXE and the generated-trainer template EXE (verified by PE icon-resource extraction against the committed ICOs). | Keep the clean-room build and release checks green after each change. |
| Master Trainer (0.21, in dev) | Full MT-1..MT-5 feature set on branch `native-0.20-master-trainer` (merged `main` @ `322ae22`): incremental table index (folder + sub-folders, sha256-bound JSON in the state home, foreign-schema/tamper refusal), cross-platform read-only process watch, pure orchestrator (unique-match auto-load, multi-table picker, fail-closed loop guard), waiting UI + handoff into the exact standalone trainer with `master_back`, per-table on/off persistence via the engine state store, `master` CLI subcommand, `Master_Trainer` icon contract. 141 master-trainer tests; dev suite 4,011 OK / 30 expected skips of 4,044. | The 0.21 build cut from the canonical path + in-build suite; user field test; MT-6/7/8 queued (settings sidecar wiring, SteamOS/CheatDeck attach route, frozen `CT2Trainer-Master.exe`). |
| Synthetic feature coverage | **42/42** declared feature classes and **7,475/7,475** action weight covered across **30 synthetic tables**. | This metric does not establish support for every original table or a real game effect. Add synthetic cases when a new behavior is found. |
| Original reference tables | All **151/151** table paths load after the RT-3 legacy-binary CT loader (2026-10-23). Local static catalog (0.20 branding cycle remeasure, run `blocked-catalog-020-icons`, 2026-10-30, frozen manifest `gap_inventory/reference-manifest.json`; zero delta vs `blocked-catalog-019-field`) classifies **116,581 supported**, including **60,161 staged**, out of **117,634 plan entries**. | **1,053 entries are blocked** (was 1,351 after RT-4.3, 1,743 after RT-4.5, 1,778 after RT-4.6, 1,807 after RT-4.4, 1,858 after RT-4.1/RT-3 and 2,698 before RT-4.1; RT-4.2 cleared the last 298 rows - R4 Lua-runtime symbol providers re-staged, R7 GetAsyncKeyState bare calls, keep-first scope fallback; zero newly blocked). The 0.19 field-fix cycle changed no catalog row (no corpus table uses `moAlwaysHideChildren`). Staged entries still need their runtime conditions proved. |
| Observed game effects | Owned fixtures and selected runtime chains have tests. | The AP-11 campaign has **0 of 6,143** game effects confirmed. Original-table behavior must be checked against pinned game builds or explicitly equivalent owned targets. |
| Final platforms | The 0.9.0-rc2 portable converter and a generated trainer were user-tested without CE or Python; later fixture tests cover many runtime paths. The 0.16 re-cut was field-tested 2026-10-21 (new WP-58 UI confirmed good; one cheat = table/build mismatch, no fix; the state-lock orphan after a blocked close was fixed in code the same day, see the ledger). The Sinking City 2 table-load warnings were made accurate in 0.16.1 (2026-10-21): table-version reference 45 → 46 field-verified, `{$LUA}`/`ShellExecute` wording now states the supported native behavior — the table itself loaded fine (see the ledger). The 0.16.1 field test (2026-10-21, Sinking City 2) exposed a startup block behind a stale `state.lock`: WP-57 hook journals with `captured_placeholders` failed the recovery schema; fixed on `main` 2026-10-22 (0.16.2, built as `native-20261022T160328Z-0423fb21` — see the ledger). The 0.16.2 field test (2026-10-22, Sinking City 2) exposed the next activation failure: the startup brick from the still-missing journal field `value_data_ranges` plus a module-snapshot retry aimed at the wrong Win32 code (mislabeled 24 instead of 1116) without backoff while the game was still loading DLLs (field log: Win32 error 24 nine ms after attach); both root causes fixed on `main` 2026-10-23, shipped as 0.16.3 (see the ledger). The 0.18 field tests (2026-10-28/29, Sinking City 2 and South of Midnight) exposed two more issues: access violations in the real Win32 hotkey-bridge seam (the windowed trainer process crashed) and staged pointer-chain value reads failing silently (blank "unavailable" without a log trace); the South of Midnight table exposed the staged-options UI gaps (staged-pending value rows still opened the inline editor, `moAlwaysHideChildren` not implemented); both fixed in 0.19 (2026-10-30, see the ledger). | The 0.16 re-cut has no recorded full clean-machine acceptance. Clean Windows and real Steam Deck/Proton/touch acceptance remain open. `runtime_unverified` stays set. |

**The 42/42 result is real, but it measures the synthetic feature matrix.**
The 1,053 blocked entries (after the RT-4.2 remeasure, was 1,351 after
RT-4.3, 1,743 after RT-4.5, 1,778 after RT-4.6, 1,807 after RT-4.4,
1,858 after RT-4.1/RT-3 and 2,698 at the Wave-4 baseline), staged
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
   RT-4.2, RT-4.3, RT-4.4, RT-4.5 and RT-4.6 done):** RT-3
   legacy-binary CT loading
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
   dialect tests now at 38); RT-4.2 runtime provider model landed
   2026-10-27 (catalog remeasure `blocked-catalog-rt42-main`: 1,351 ->
   1,053 blocked, 298 rows cleared, zero newly blocked, 28
   reason-only changes). The RT-5 API/construct inventory is
   documented in `documentation/rt5-api-inventory.md`; RT-5 item G
   (createThread/threadWait gate decision, option 2 — gate stays, no
   thread backend this milestone) and RT-5 item F (no-effect register
   ratification, `tests/test_native_rt5_no_effect_register.py` +22)
   both landed 2026-10-26, tests-only, zero catalog movement. RT-5
   item A (embedded `<Files>` extraction), item C (bounded
   process-info Lua API family), item C2 (dynamic addresslist records +
   custom AA directives) and item D (onOpenProcess/onTableLoad
   callback dispatch) landed 2026-10-28/29 (merges `479977c`,
   `0167825`, `dde9f04`, `9294bb8`; zero catalog delta at each step).
   The 0.19 field-fix cycle (2026-10-30, merge `fbe626f`) added the
   hotkey-bridge AV fix, value-read observability, the `describe` CLI
   and full South of Midnight staged-options support on top.
   Remaining: the RT-5 implementation items B (CheatCodes
   code-patch plan path or recorded scope decision) and E
   (`messageDialog` no-op-with-review vs refusal decision).
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
