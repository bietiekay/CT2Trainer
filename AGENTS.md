# Project Handoff for Further Agents

**Start with the plain-language [current status](STATUS.md).** It summarizes
what is proven and what remains open; `plans/TRACKING.md` remains the
detailed source of truth. The root integrator must update `STATUS.md` in
the same change as `plans/TRACKING.md` and
`documentation/native-progress.md` whenever a package changes catalog or
feature-matrix counts, an AP-11/game or Windows/Deck observation is
recorded, or a build/release is cut. Record the evidence date, exact build
or source revision, input/run identifier and denominator. Keep synthetic
coverage, original-table static coverage and observed effect separate.
Do not report the reference-table goal as complete from the 42/42
synthetic matrix or carry stale counts into this overview.

**Active outcome (2026-10-26): 100% of the 151 local-only reference-table
paths (143 distinct hashes) must load and support their intended behavior
through an independent clean-room implementation.** 0.26 released
(build `native-20261103T112811Z-59a6b3d5` cut from `main` @
`c114ec2`, 2026-11-03): the Master Trainer waiting-view usability
MT-13/14/15 - search/filter/sort through the new pure
`table_filter.py` layer, keyboard load flow, rolling recent tables in
`master-settings.json` schema 3 + Size/Modified/Last-used columns -
plus the live-target takeover field fix (stale-lock recovery now
attaches to the still-running game behind one user-confirmed prompt
when the owner is proven dead and only target-side identities remain
unproven); +61 tests, full main suite 4,320 OK / 30 expected skips,
catalog zero delta `blocked-catalog-026-master-ui`; in-build suite
4,320 OK / 30 expected skips, `ce_inputs: []`; superseded 0.25
(build `native-20261103T062439Z-f4c16be9`). 0.27 released (build
`native-20261103T145543Z-b29b3688` cut from `main` @ `8aa0815`,
2026-11-03): the Master Trainer waiting-view settings
persistence (MT-16: `master-settings.json` schema 3 → 4 -
`view_filter` / `view_sort` / `view_mode` restored at start and
persisted on every change; schema-1/2/3 documents promote, a
schema-3 document carrying a view_* field is refused as an unknown
field) + the process-grouped waiting view (MT-17: the pure
`group_tables_by_process` reshaping, the "View: list/process" cycle
button, display-only group rows); +22 tests, full main suite 4,342
OK / 30 expected skips, catalog zero delta
`blocked-catalog-027-view`; in-build suite 4,342
OK / 30 expected skips, `ce_inputs: []`, `runtime_unverified`
deliberately kept per gate; source ZIP `CT2Trainer-0.27-source.zip`
sha256 `264b42d6c42dac1bb434c1d0591e82ac0bec69e61e1a1c75047c6aa58126f40e`
(14,357,294 bytes) - carries the MT-16/17 waiting-view settings and
the process groups - and portable ZIP
`CT2Trainer-0.27-windows-portable.zip` sha256
`bfcf2abc885122dfa8653fcfd0046323e7112f59c0850958688e36e014ebc135`
(49,654,613 bytes; the frozen `CT2Trainer-Master.exe` (sha256
`9762c8bdc2298c16bd82779f206d9a885a449261a6428187c3bd2155fc5bf1bc`,
16,929,639 bytes) ships next to the converter); superseded 0.26
(build `native-20261103T112811Z-59a6b3d5`). 0.28 released (build
`native-20261103T161621Z-ea8fde2f` cut from `main` @ `d7f4cf0`,
2026-11-03): the Master Trainer pinned/favorite tables
(MT-18: `master-settings.json` schema 4 → 5 - `pinned_tables`
persisted, most recent pin first, cap `PINNED_TABLES_LIMIT` = 25,
schema-4 documents promote, a schema-4 document carrying the field
is refused as an unknown field; the row context menu "Pin to top" /
"Unpin" toggle with immediate persist and named refusals; the pure
`table_filter.pin_tables` reshaping - pinned rows first in pin
order, the remainder keeps the input order, unknown pin paths
ignored; a pinned table floats to the top of the list view and to
the top of its process group, the pin marker lives in the detail
column); +15 tests, full main suite 4,357 OK / 30 expected skips,
catalog zero delta `blocked-catalog-028-pin`; in-build suite 4,357
OK / 30 expected skips, `ce_inputs: []`, `runtime_unverified`
deliberately kept per gate; source ZIP
`CT2Trainer-0.28-source.zip` sha256
`13f4b2222a83f9e4588d388b4120beaf8018a091a05364029ae2a950c0dabb1a`
(14,363,765 bytes) - carries the MT-18 pinned tables - and
portable ZIP `CT2Trainer-0.28-windows-portable.zip` sha256
`d656835a69ece75ff6adaa5ce766385327fb9ec08d89837ad772425dafe91ce3`
(49,658,473 bytes; the frozen `CT2Trainer-Master.exe` (sha256
`c12dcea5bb8a609dae4df36f44827ab5269c9e1015cb723067ed98dc100bf99b`,
16,929,732 bytes) ships next to the converter); superseded 0.27
(build `native-20261103T145543Z-b29b3688`). 0.29 released
(build `native-20261104T094808Z-50af0517` cut from `main` @
`de3e4ff`, 2026-11-04): the Master Trainer UI/UX revamp
(MT-19 trainer-focus mode: the whole waiting view lives in one
container frame destroyed on trainer entry - the table list no
longer shares the window with the trainer rows, the trainer row
grid owns the full window, rebuilt whole on the way back; MT-20
discoverability: the read-only "UI flow" header button - the
in-app copy of the reviewable UI.md, F5 re-scan from anywhere in
the waiting view, initial table-list focus, "Retry load" moved
into the status bar; the reviewable full-flow document ships as
master_trainer/UI.md in the source ZIP); +13 tests, full main
suite 4,370 OK / 30 expected skips; catalog zero delta
`blocked-catalog-029-trainer-focus`; in-build suite 4,370
OK / 30 expected skips, `ce_inputs: []`, `runtime_unverified`
deliberately kept per gate; source ZIP
`CT2Trainer-0.29-source.zip` sha256
`2f5ce6e446f8d9885cd653580b5e194a2a0fc524eba7b5f684fe1f1a0e1da3d4`
(14,378,934 bytes) - carries the MT-19/20 trainer-focus +
discoverability and the reviewable `master_trainer/UI.md` - and
portable ZIP `CT2Trainer-0.29-windows-portable.zip` sha256
`98c63c368bc2cccd68335e9db94a3b897abbbb815730c97912e3068805fad226`
(49,667,528 bytes; the frozen `CT2Trainer-Master.exe` (sha256
`88e6ee99aa4c46973945e462ca956977e9942a1e8b30630aa2570107540f2de8`,
16,937,063 bytes) ships next to the converter); superseded 0.28
(build `native-20261103T161621Z-ea8fde2f`). 0.30 released
(build `native-20261104T131114Z-11522f68` cut from `main` @
`2fbca94`, 2026-11-04): the Master Trainer table details + live
load-gate preview (MT-22: right-clicking a waiting-view row offers
"Table details" first - the read-only Toplevel with the indexed
facts for the table (path, folder, size, modified, bound processes,
index status, pin, last used, running PIDs, content sha) plus the
on-demand `gate_table_for_load` re-check - the same pass MT-9 runs
at load time, named refusal code + displayable detail; the pure
`table_details.py` row builder; single window, lift on second
open, closed on trainer entry); +16 tests, full main suite 4,386
OK / 30 expected skips, catalog zero delta
`blocked-catalog-030-details`; in-build suite 4,386
OK / 30 expected skips, `ce_inputs: []`, `runtime_unverified`
deliberately kept per gate; source ZIP
`CT2Trainer-0.30-source.zip` sha256
`091b379c132e277c19f519705dcccc4c0817e8e7e614e5baf2f14bbe3fe414a3`
(14,387,690 bytes) - carries the MT-22 table details +
load-gate preview and the reviewable `master_trainer/UI.md` - and
portable ZIP `CT2Trainer-0.30-windows-portable.zip` sha256
`f4476bb08e3e65e6db9cd35bfe7a72408a555b8525bd6a10f8b794f943083d54`
(49,669,933 bytes; the frozen `CT2Trainer-Master.exe` (sha256
`9d0a525a78dfbfffb906261ad42e435c5414cb6cb0189dd78c73910063f67643`,
16,940,058 bytes) ships next to the converter); superseded 0.29
(build `native-20261104T094808Z-50af0517`). 0.31 released (build
`native-20261105T080853Z-2e7f50a5` cut from `main` @ `2def12f`,
2026-11-05): the Master Trainer per-table live status
+ color coding + status filter (MT-23: the waiting-view Status
column shows the table's state right now - one bounded stat per
visible row per render against the index entry - ok / running /
changed / missing / unreadable, cheapest fact first, live facts
outrank the cached scan state, same order the MT-9 gate proves;
row color coding amber for changed / red for missing-unreadable;
persisted "Status: all / ok / attention" header cycle, master-state
schema 5 to 6, view_status; the pure `table_status.py` decision
layer); +28 tests, full main suite 4,414 OK / 30 expected skips,
catalog zero delta `blocked-catalog-031-status`; in-build suite
4,414 OK / 30 expected skips, `ce_inputs: []`, `runtime_unverified`
deliberately kept per gate; source ZIP
`CT2Trainer-0.31-source.zip` sha256
`3bab9648208f6ed4cbafa919991cab19c7921597ac2075c5c8b964e17258c0f9`
(14,398,817 bytes) - carries the MT-23 per-table live status +
color coding + status filter and the reviewable
`master_trainer/UI.md` - and portable ZIP
`CT2Trainer-0.31-windows-portable.zip` sha256
`df5581ec5e8b0c0b99abdf35b914f08ec138b4470234b48c615304419a970839`
(49,679,202 bytes; the frozen `CT2Trainer-Master.exe` (sha256
`811c0f85c143b632dd182646282ddb32c3293513a665eb62c8055f74f9c89dcb`,
16,948,380 bytes) ships next to the converter); superseded 0.30
(build `native-20261104T131114Z-11522f68`). 0.32 released (build
`native-20261108T100731Z-a1d311e5` cut from `main` @ `bfcc3a3`,
2026-11-08): the Master Trainer per-table entry count +
blocked count via background plan analysis (MT-24: the
waiting-view Entries / Blocked columns - the actionable and blocked
record counts of the plan compile, computed in one background daemon
thread through the tested `compile_table` plan path, no Lua
execution, no target attach, the same static proof the corpus audit
uses; persisted in `table-analysis.json` keyed by table content
sha256, LRU-bounded; the meta line shows the live "analyzing N
table(s)" figure; the MT-22 table-details window gains the analysis
block; display-side only, never blocks / alters / delays the MT-9
load gate); +69 tests, full main suite 4,483 OK / 30 expected
skips, catalog zero delta `blocked-catalog-032-analysis`; in-build
suite 4,483 OK / 30 expected skips, `ce_inputs: []`,
`runtime_unverified` deliberately kept per gate; source ZIP
`CT2Trainer-0.32-source.zip` sha256
`f6cae57590d083e37308bc4a03b1046b8186617bdb0f98c88c9bc324404493d9`
(14,426,224 bytes) - carries the MT-24 Entries / Blocked columns,
`table_analysis.py` + `analysis_worker.py` (incl. the
`active_workers()` live-worker registry), the mt23 worker-guard
test fix and the reviewable `master_trainer/UI.md` - and portable
ZIP `CT2Trainer-0.32-windows-portable.zip` sha256
`3a7980ba04f60f7cb93edce3cf5c723ba609ff55a00b1f866079101d3b7bc986`
(49,699,633 bytes; the frozen `CT2Trainer-Master.exe` (sha256
`6dc34408c8e5ecec1c2215c45da27ea22cc5c5ce5a9629267778b172d44d3485`,
16,966,114 bytes) ships next to the converter); superseded 0.31
(build `native-20261105T080853Z-2e7f50a5`). 0.33 content on main
(2026-11-08, root-direct): the Master Trainer table folder
auto-rescan (MT-25: the waiting view re-runs the existing
incremental scan every 30 s while the persisted "Auto-rescan: on"
status-bar toggle is on - added / changed / removed tables show up
without a manual F5; the same (size, mtime_ns) + sha256 short-circuit
contract as the manual Rescan, one stat pass per interval, polling
only (no OS file-watcher), paused on trainer entry; the interval clock
restarts on a manual rescan, a folder change, and the waiting-view
rebuild; zero load-path effect - the MT-9 gate re-checks the table
independently at load time; master-state schema 6 -> 7, auto_rescan);
+16 tests, full main suite 4,499 OK / 30 expected skips, catalog zero
delta `blocked-catalog-033-auto-rescan`; the 0.33 build is cut from
this content (0.32 remains the latest verified release). The 0.16
Wave-4
feature work is complete; RT-4.1 (symbol provider fidelity) landed on
`main` 2026-10-22; RT-3 (legacy-binary CT loader; `SuperMeatBoy.CT`
now loads, table load 151/151) landed on `main` 2026-10-23; RT-4.4
(value semantics), RT-4.6 (input legacy & authoring gaps) and RT-4.5
(AA directive & script coverage) landed on `main` 2026-10-24; RT-4.3
(address expression & identifier dialect) landed on `main` 2026-10-26
(plus its dedicated dialect test follow-up); RT-4.2 (runtime provider
model: keep-first duplicate-provider scope fallback, mixed-dialect
unregistersymbol release evidence, bounded API-export registry with
link-time resolution) landed on `main` 2026-10-27, completing RT-4;
RT-5 item G
(createThread/threadWait gate decision, option 2: the capability gate
stays, no thread backend ships this milestone) and item F (no-effect
register ratification, tests only) landed on `main` 2026-10-26; RT-5
item A (embedded `<Files>` extraction: new `embedded_files.py`
dual-branch codec, fail-closed table-load decode, `findTableFile` /
`readStringLocal` / stringstream / stringlist Lua surface, +53 tests)
landed on `main` 2026-10-28 (merge `479977c`). RT-5 item C (bounded
process-info Lua API family: 11 CE 7.5 process-info APIs under the
clean-room single-target model — getProcessIDFromProcessName,
getProcessList, getAutoAttachList, getOpenedProcessID, getSettings,
integerToUserData, targetIs64Bit, enumModules, disassemble,
stringlist_add, getCEVersion pinned '7.5' — item-A-style allowlist
wiring, +23 tests) landed on `main` 2026-10-28 (commit `0167825`,
full main suite 3,790 OK / 25 expected skips, zero catalog delta
`blocked-catalog-rt5c-main`). RT-5 item C2 (dynamic addresslist records
+ custom AA directives: createMemoryRecord session journal with
synthetic IDs >= 2**31 never persisted, CE MemoryRecord runtime surface
incl. Parent/Child/Offset/Value vtByte..vtDouble, journal + plan-record
OnActivate/OnDeactivate callbacks, getCEVersion number 7.5 superseding
the item-C string pin, addresslist getMemoryRecord/Count/
MemoryRecord[i] lookups, registerAutoAssemblerCommand custom directives
table-scope with built-in names refused, +27 tests) landed on `main`
2026-10-29 (merge `dde9f04`, full main suite 3,817 OK / 25 expected
skips, zero catalog delta `blocked-catalog-rt5c2-main`). RT-5 item D (onOpenProcess/onTableLoad callback dispatch: CE-sequence table-scope dispatch after a clean table-Lua bootstrap - onOpenProcess with the attached target PID, onTableLoad with the Lua literal false, documented bounded deviation: no before-load phase; pcall-wrapped dispatch chunks with literal argument injection, 'absent'/'ok'/'error: <msg>' -> no event / table-callback / table-callback-error, throwing-callback containment with plan byte-identity, idempotent per confirmed attach with re-attach re-fire, +9 tests) landed on `main` 2026-10-29 (merge `9294bb8`, full main suite 3,826 OK / 25 expected skips, zero catalog delta `blocked-catalog-rt5d-main`). The 0.19 field-fix cycle (2026-10-30, branch `native-0.19-field-fix`, merge `fbe626f`) shipped the Sinking City 2 hotkey-bridge Windows AV fix (HWND_MESSAGE corrected to -3, explicit Win32 argtypes/restype, guarded hotkey registration, +1 real-seam regression test), value-read observability (`read_value` logs `value-read-failed` per identifier per cause, dedup, re-raise), the new `describe` CLI subcommand (+13 tests), and full staged-options support for the South of Midnight table (two-level cascade proof +2 tests, staged-pending tap guard, moAlwaysHideChildren pass-through `hidden_children` marker + row-model subtree suppression, +8 UI tests); full main suite 3,850 OK / 26 expected skips, zero catalog delta `blocked-catalog-019-field`. The 0.20/0.20.1 branding-icon releases (2026-10-30/31; branch `native-0.20-icons` merged at `6298803`, 0.20.1 re-cut commit `080128c`, build `native-20261031T104114Z-d64ae4c2`) shipped the user-provided `CT2Trainer_Generator` icon for the tool EXE and the `Standalone_Trainer` icon embedded in the template stub so every generated trainer carries it; in-build suite 3,854 OK / 26 expected skips, zero catalog delta `blocked-catalog-020-icons`. RT-5 item B (CheatCodes code-patch plan path: fail-closed per-entry parse, `code_patch` plan records with synthetic IDs at 2**32+, engine toggle lifecycle with named refusals, +26 tests) landed on `main` 2026-10-31 (merge `9ef4a74`, full main suite 3,880 OK / 26 expected skips) and RT-5 item E (messageDialog safe logged no-op with CE argument shapes, nil tolerance, `message-dialog` debug event, both spellings in record + table scope, +22 tests) landed on `main` 2026-10-31 (merge `b8bb4ee`, full main suite 3,902 OK / 26 expected skips) — with B and E every RT-5 inventory item (A, B, C, C2, D, E, F, G) has landed, RT-5 complete; the closing CE 7.5 vs CT2Trainer analysis landed 2026-10-31 (merge `322ae22`). The 0.21 Master Trainer (the all-in-one "Forever Master Trainer" front end: incremental folder table index with per-table process mapping, cross-platform process watch, unique-match auto-load / multi-table picker, handoff into the exact standalone trainer UI, per-table on/off persistence on the engine state store; MT-1..MT-5, 141 tests, zero catalog effect) merged into `main` 2026-10-31 (merge `9a725a8`) and shipped in the 0.21 build (run `native-20261031T211046Z-14707e12`, in-build suite 4,044 OK / 30 expected skips, fully green at the canonical path). The 0.22 FO4 field-fix cycle
(2026-11-01, branch `native-0.21-fo4-rearm`, merge `a12a0b6`) shipped the
bounded automatic re-arm of ScanMiss enable failures (30 s x 10
attempts, budget reset per (re-)attach, armed set survives target
exit), the manual "Try again" row action and the top-level "Re-attach"
action (+17 tests; full main suite 4,061 OK / 30 expected skips, zero
catalog delta `blocked-catalog-022-rearm`); the 2026-10-30/31 field-test
logs (Fallout 4 on 0.20, The Sinking City 2 on 0.19 - 3 sessions)
additionally exposed SC2 hotkey-bridge defects (unguarded
RegisterHotKeyW missing-export path, engine-blocking hotkey failure,
deterministic close-timeout + AV in the message loop, transient-read
PatchConflict Win32 299, state-lock first-restart refusal) recorded in
`documentation/native-progress.md` (section 0.22 field cycle) and
deferred to the next field-fix cycle (hotkey-bridge code unchanged in
0.22); the 0.22 build (run `native-20261101T075049Z-f32c112d`, cut from
`main` @ `2b24a1c`, 2026-11-01) is green in-build at 4,061 OK / 30
expected skips with `ce_inputs: []`. The 0.23 Master Trainer roadmap
completion (2026-11-01, branch `native-0.23-master-roadmap`, main @
`b2d0344`) ships MT-6 (per-table settings sidecar keyed by table
content sha256 under the state home, restore-on-load / save-on-close,
named refusals), MT-7 (documented SteamOS/CheatDeck target route:
named fail-closed non-Windows attach refusals, NOT a Linux attach
backend; the real Deck protocol run stays root/user field work) and
MT-8 (frozen `CT2Trainer-Master.exe` with the `Master_Trainer.ico`,
now emitted by every build into the run folder and the portable
ZIP), plus the waiting-view observability (metadata line, live
"Running now" line, running/PID tree markers) and the
ask-on-first-start table-folder parameter (`master-settings.json`
persisted in the state home; an explicit folder argument always
wins); no new trainer functionality; then the MT-9 load-time table
compatibility & size gate (branch `native-0.23-load-gate`, merge
`98a9226`: `table_gate.py` re-proves the table file against its
index entry at load request - missing / not-a-file / read failure /
empty / over the 32 MiB limit / changed since last scan / not
loadable by the tested parser / changed during analysis; stable
named codes + displayable detail; the named `TableLoadGateRefusal`
from the default plan compiler fails the load through the
orchestrator's fail-closed loop guard - no crash, named dialog +
status line, no hot-retry, Rescan / Retry re-arm, no picker
re-issue for a failed pair; +22 tests), plus the same-day field
fixes (placeholder headings no longer create plan-level symbol
dependencies, `28c9b57`, +10 tests; the SC2 hotkey-bridge field
fix from the 0.22.1 lane - T1 named missing-export guard, T2 engine
containment, T3 loop-thread close protocol, T7 persistence
ordering - merge `4e9b95b`, +11 tests); full main suite 4,176 OK /
30 expected skips, zero catalog delta on all three remeasures
(`blocked-catalog-023-master-roadmap`, `blocked-catalog-023-load-gate`,
`blocked-catalog-023-field-fixes`); the 0.23 build (run
`native-20261101T145310Z-a160bae4`, cut from `main` @ `6e3ec98`,
2026-11-01) is green in-build at 4,176 OK / 30 expected skips with
`ce_inputs: []` - the frozen `CT2Trainer-Master.exe` ships in the
run folder, the payload inventory and the portable ZIP.
The RT-5 API/construct inventory is
documented in `documentation/rt5-api-inventory.md`. The
latest original-table catalog (run `blocked-catalog-020-rt5-be`,
2026-10-31) has 1,053 blocked of 117,809 plan entries, 116,756 supported
(60,161 staged) and zero load errors (+175 supported vs
`blocked-catalog-020-icons` - the 175 `CodeEntry` records of the 22
CheatCodes tables are now supported `code_patch` rows; zero newly
blocked, zero reason changes; previous: 1,053 after RT-5 item D and the
0.19/0.20/0.20.1 zero-delta cycles, 1,351 after RT-4.3, 1,743 after RT-4.5,
1,778 after RT-4.6, 1,807 after RT-4.4, 1,858 after RT-4.1/RT-3; original
baseline: 2,698 blocked, 58,950 staged). The 42/42 feature
matrix measures only the 30 pinned synthetic cases; AP-11 has 0/6,143
confirmed game effects. Read
[`plans/reference-table-100-roadmap.md`](plans/reference-table-100-roadmap.md)
for the active RT-1…RT-7 work and completion gates. Historical AP/WP
plans remain useful design records, not the current goal queue.
The requested parity scope is trainer/cheat handling and game-facing
effects; CE visual UI and editor features are outside scope unless a
table's UI API carries a game-facing action. The initial general
[capability assessment](documentation/ce-feature-parity-assessment.md)
records known gaps and the measurement method.

**All repository documentation and workflow content is English-only
(2026-10-07, user decision).** Every doc, plan, ledger, tool message and
artifact string is maintained in English from now on, regardless of the
language used in chat.

**CT2Trainer (status 2026-11-08, 0.33 content on main - the 0.33
build is cut from this content; 0.32 remains the latest verified
release, build `native-20261108T100731Z-a1d311e5` cut from `main` @
`bfcc3a3`, 2026-11-08, in-build suite 4,483 OK / 30 expected skips,
`ce_inputs: []`) - 0.33 Master Trainer table folder auto-rescan
(MT-25: the waiting view re-runs the existing incremental scan every
30 s while the persisted "Auto-rescan: on" status-bar toggle is on -
added / changed / removed tables show up without a manual F5; the
same (size, mtime_ns) + sha256 short-circuit contract as the manual
Rescan, one stat pass per interval, polling only (no OS
file-watcher), paused on trainer entry; the interval clock restarts
on a manual rescan, a folder change, and the waiting-view rebuild;
zero load-path effect - the MT-9 gate re-checks the table
independently at load time; master-state schema 6 -> 7, auto_rescan,
default on); +16 tests, full main suite 4,499 OK / 30 expected
skips; catalog zero delta
`blocked-catalog-033-auto-rescan`), superseded 0.32 released (build
`native-20261108T100731Z-a1d311e5` cut from `main` @ `bfcc3a3`,
2026-11-08) - 0.32 Master Trainer per-table entry count +
blocked count via background plan analysis (MT-24: the waiting-view
Entries / Blocked columns - the actionable and blocked record counts
of the plan compile, computed in one background daemon thread through
the tested `compile_table` plan path - no Lua execution, no target
attach, the same static proof the corpus audit uses; persisted in
`table-analysis.json` keyed by table content sha256, LRU-bounded to
1024 entries, top-8 blocked reasons per table; the meta line shows
the live "analyzing N table(s)" figure; the MT-22 table-details
window gains the analysis block; display-side only - never blocks,
alters, or delays the MT-9 load gate, which re-checks the table
independently at load time); +69 tests, full main suite 4,483 OK /
30 expected skips; catalog zero delta
`blocked-catalog-032-analysis`), superseded 0.31 released (build
`native-20261105T080853Z-2e7f50a5` cut from `main` @ `2def12f`,
2026-11-05) - 0.31 Master Trainer per-table live status +
color coding + status filter (MT-23: the waiting-view Status column
shows the table's state right now - one bounded stat per visible row
per render against the index entry: ok / running / changed /
missing / unreadable, cheapest fact first, live facts outrank the
cached scan state, the same order the MT-9 gate proves at load time;
row color coding (amber `#e5c07b` for changed, red `#ff7b72` for
missing / unreadable); the persisted "Status: all / ok / attention"
header cycle (master-state schema 5 -> 6, `view_status`); the pure
`table_status.py` decision layer); +28 tests, full main suite 4,414
OK / 30 expected skips; catalog zero delta
`blocked-catalog-031-status`), superseded 0.30 released (build
`native-20261104T131114Z-11522f68` cut from `main` @ `2fbca94`,
2026-11-04) - 0.30 Master Trainer table details + live
load-gate preview (MT-22: right-clicking a waiting-view row offers
"Table details" first - the read-only Toplevel with the indexed
facts for the table (path, folder, size, modified, bound processes,
index status, pin, last used, running PIDs, content sha) plus the
on-demand `gate_table_for_load` re-check - the same pass MT-9 runs
at load time, named refusal code + displayable detail; the pure
`table_details.py` row builder; single window, lift on second
open, closed on trainer entry); +16 tests, full main suite 4,386
OK / 30 expected skips; catalog zero delta
`blocked-catalog-030-details`), superseded 0.29 released (build
`native-20261104T094808Z-50af0517` cut from `main` @ `de3e4ff`,
2026-11-04) - 0.29 Master Trainer UI/UX revamp (MT-19
trainer-focus mode: the whole waiting view lives in one container
frame destroyed on trainer entry - the table list no longer shares
the window with the trainer rows, the trainer row grid owns the
full window, rebuilt whole on the way back; MT-20 discoverability:
the read-only "UI flow" header button - the in-app copy of the
reviewable UI.md, F5 re-scan from anywhere in the waiting view,
initial table-list focus, "Retry load" moved into the status bar;
the reviewable full-flow document ships as master_trainer/UI.md in
the source ZIP); +13 tests, full main suite 4,370 OK / 30 expected
skips; catalog zero delta
`blocked-catalog-029-trainer-focus`), superseded 0.28 released
(build
`native-20261103T161621Z-ea8fde2f` cut from `main` @ `d7f4cf0`,
2026-11-03) - 0.28 Master Trainer pinned/favorite tables
(MT-18: `master-settings.json` schema 4 → 5 - `pinned_tables`
persisted, most recent pin first, cap 25; the row context menu
"Pin to top" / "Unpin" toggle, pinned tables float to the top of the
list view and to the top of their process group, pin marker in the
detail column, pure `pin_tables` layer); +15 tests, full main suite
4,357 OK / 30 expected skips; catalog zero delta
`blocked-catalog-028-pin`), superseded 0.27 released (build
`native-20261103T145543Z-b29b3688` cut from `main` @ `8aa0815`,
2026-11-03) - the 0.27 Master Trainer waiting-view settings
persistence (MT-16: `master-settings.json` schema 3 → 4 - the filter
query, sort mode and view mode restored at start and persisted on
every change) + the process-grouped waiting view (MT-17: group-
by-bound-process tree, display-only group rows); +22 tests, full
main suite 4,342 OK / 30 expected skips; catalog zero delta
`blocked-catalog-027-view`), 0.26 released (build
`native-20261103T112811Z-59a6b3d5` cut from `main` @ `c114ec2`,
2026-11-03) - the 0.26 Master Trainer waiting-view usability
MT-13/14/15 (search/filter/sort through the new pure
`table_filter.py` layer, keyboard load flow, rolling recent tables in
`master-settings.json` schema 3 + Size/Modified/Last-used columns,
+42 tests) plus the live-target takeover field fix (stale-lock
recovery attaches to the still-running game behind one
user-confirmed prompt when the owner is proven dead and only
target-side identities remain unproven; +19 tests); full main suite
4,320 OK / 30 expected skips; catalog zero delta
`blocked-catalog-026-master-ui`), 0.25 released (build
`native-20261103T062439Z-f4c16be9` cut from `main` @ `a861bfb`,
2026-11-03, in-build suite 4,259 OK / 30 expected skips,
`ce_inputs: []`) - Master
Trainer user control MT-10/11/12 (explicit table load, process
picker + persisted attach mode, detach/user attach); online feature
evaluation in `master_trainer/ROADMAP.md`; Tcl test-harness hardening
(test-only); in-build reliability fix (state-home isolation in the
`run_master` cancel test + explicit-master Tk variables in
`master_ui.py`; the first in-build run
`native-20261102T181843Z-ddfb63f0` exposed the dependence); +66 tests;
catalog zero delta `blocked-catalog-025-master-ui`), 0.24 released
as the superseded build (trainer tick sounds - user field request
2026-11-01; clean-room in-code tick
synthesis for on/off/attach in `trainer_sounds.py`, `ui.py` rewired
(row switch + group heading toggle + attach-success transition in
`TrainerWindow.poll()`), `engine.py` `pop_hotkey_ui_toggles()`
surfaces confirmed hotkey activation toggles, branch
`native-0.24-trainer-sounds`, +21 tests, full main suite 4,193 OK /
30 expected skips, zero catalog delta `blocked-catalog-024-sounds`;
the 0.24 build `native-20261102T102029Z-fe358e35` was cut from
`main` @ `a2777ed` - in-build suite 4,193 OK / 30 expected skips,
`ce_inputs: []`); superseded 0.23 released (full Master
Trainer roadmap: MT-6 per-table settings sidecar (content-sha keyed,
restore-on-load / save-on-close) + MT-7 documented SteamOS/CheatDeck
target route (named fail-closed non-Windows attach refusals, NOT a
Linux attach backend) + MT-8 frozen `CT2Trainer-Master.exe` now part
of every build + MT-9 load-time table compatibility & size gate
(stable named refusals, fail-closed loop guard, no hot-retry) +
waiting-view observability + ask-on-first-start table-folder
parameter + same-day field fixes (placeholder-heading symbol-
dependency skip 28c9b57 +10 tests; SC2 hotkey-bridge field fix
0.22.1 lane merge 4e9b95b +11 tests), branch
`native-0.23-master-roadmap` @ b2d0344 + load-gate branch
`native-0.23-load-gate` @ 98a9226, main @ 6e3ec98, +115 tests, full
main suite 4,176 OK / 30 expected skips, zero catalog delta
`blocked-catalog-023-field-fixes`); latest
verified release 0.26 (build
`native-20261103T112811Z-59a6b3d5` cut from `main` @ `c114ec2`,
2026-11-03 - the 0.26 Master Trainer waiting-view usability
release, in-build suite 4,320 OK / 30 expected skips,
`ce_inputs: []`, source ZIP `CT2Trainer-0.26-source.zip` sha256
3d62f80cdfb95d8439d4a2f2150002976795faad313fa75d47aeb4fb92bb49bd
(14,348,462 bytes), portable ZIP
`CT2Trainer-0.26-windows-portable.zip` sha256
49be1d286999ed175737edb073c5ab83533c40cccc7e636685a256a0b07004b3
(49,653,968 bytes), frozen `CT2Trainer-Master.exe` (sha256
895f937ed5c228c09b97edba28aa9dc4ad228abd58585f73080f40ab265bc031,
16,925,677 bytes) in the run folder, the payload inventory and the
portable ZIP); superseded 0.25 (build
`native-20261103T062439Z-f4c16be9` cut from `main` @ `a861bfb`,
2026-11-03 - the 0.25 Master Trainer user-control release, in-build
suite 4,259 OK / 30 expected skips, `ce_inputs: []`, source ZIP
`CT2Trainer-0.25-source.zip` sha256
64f8c3082cff50687b1962234c17a82e2a2f0c19eb1112ece06a0a25132f35be
(14,324,774 bytes), portable ZIP
`CT2Trainer-0.25-windows-portable.zip` sha256
774266f7e2c9dc69f4d8cfc963309b9907442ec6b5343ff629b9e30c04049653
(49,633,196 bytes), frozen `CT2Trainer-Master.exe` (sha256
8736f73e762b57a8f337bf8fa04c2c16f8622c4d99e7dd7f2167b2c9999e3d8f,
16,912,561 bytes) in the run folder, the payload inventory and the
portable ZIP); superseded 0.24 (build
`native-20261102T102029Z-fe358e35` cut from `main` @ `a2777ed`,
2026-11-02 - the 0.24 trainer tick sounds release, in-build suite
4,193 OK / 30 expected skips, `ce_inputs: []`, source ZIP
`CT2Trainer-0.24-source.zip` sha256
dfdd8cfcca90a2789bf544d8f8de4e34941067feeb2b32ce8d550f98e5bc4eb6
14,298,696 bytes, portable ZIP
`CT2Trainer-0.24-windows-portable.zip` sha256
12262cf16e906c3811ade0a8c582b7a1057c834a3110aff004dfd13b3067e7ab
49,618,009 bytes, frozen `CT2Trainer-Master.exe` (sha256
5f3a66400c2c1775e6fc50ad6bbbc36aa8a6bcf8b58fe56507117dc33683494d,
16,896,995 bytes) in the run folder, the payload inventory and the
portable ZIP); superseded 0.23 (build
`native-20261101T145310Z-a160bae4` cut from `main` @ `6e3ec98` - the
0.23 Master Trainer roadmap release, in-build suite 4,176 OK / 30
expected skips, `ce_inputs: []`, source ZIP
`CT2Trainer-0.23-source.zip` sha256 3360cab031cb1334dda71bb02a511170a9a70d1f583b5a8721624f46e24da464
14,291,040 bytes, portable ZIP
`CT2Trainer-0.23-windows-portable.zip` sha256
eec023ba09e8fcb80608736896f0477f4a783034046e6ad67514e96ed0a2905b
49,609,916 bytes, frozen `CT2Trainer-Master.exe` in the run folder,
payload inventory and portable ZIP); superseded 0.22 (build
`native-20261101T075049Z-f32c112d` cut from `main` @ `2b24a1c` - the
0.22 FO4 field-fix cycle release: bounded automatic re-arm of
ScanMiss enable failures (30 s x 10 attempts, budget reset per
(re-)attach, armed set survives target exit) + manual Try again /
Re-attach actions (merge a12a0b6, +17 tests, in-build suite 4,061 OK
/ 30 expected skips, zero catalog delta blocked-catalog-022-rearm;
SC2 0.19 hotkey-bridge field findings recorded, fixes shipped in
0.23 via the 0.22.1 lane); superseded 0.21 (build
`native-20261031T211046Z-14707e12` cut from `main` @ `9a725a8` - the
0.21 feature release: RT-5 complete (item B CheatCodes code-patch
plan path (merge `9ef4a74`, +26 tests, catalog
`blocked-catalog-020-rt5-be`: 117,809 total / 116,756 supported /
1,053 blocked, +175 supported, zero newly blocked) + item E messageDialog
safe logged no-op (merge `b8bb4ee`, +22 tests, zero catalog delta
`blocked-catalog-rt5e-iteme`)) plus the new Master Trainer (MT-1..MT-5
feature set: incremental folder table index, cross-platform process
watch, unique-match auto-load / multi-table picker, handoff into the
exact standalone trainer UI, per-table on/off persistence, 141 tests,
zero catalog effect); in-build suite 4,044 OK / 30 expected skips,
`ce_inputs: []`); superseded 0.20.1
(build `native-20261031T104114Z-d64ae4c2` cut from `main` @ `080128c`
- the 0.20.1 release-content re-cut of the 0.20
branding-icon release: 0.20 changelog suite line corrected to the
verified in-build suite (3,854 OK / 26 expected skips, fully green at
the canonical path) + catalog remeasure `blocked-catalog-020-icons`
(zero delta) cited; in-build suite 3,854 OK / 26 expected skips,
`ce_inputs: []`); previous 0.20
`native-20261030T184820Z-b9d6dc07` @ `6298803` - the branding icons
(user-provided CT2Trainer_Generator icon set for the tool EXE,
Standalone_Trainer icon set embedded in the template stub so every
generated trainer carries it; 1024x1024 PNG masters committed,
multi-size ICOs rebuilt, +4 tests); previous 0.19
`native-20261030T121918Z-c72dbb38` @ `fbe626f` - the 0.19
field-fix cycle: Sinking City 2 hotkey-bridge Windows AV fix (HWND_MESSAGE
corrected to -3, explicit Win32 argtypes/restype, guarded hotkey
registration, real-seam regression test), value-read observability
(`value-read-failed` log event per identifier per cause), the `describe`
CLI subcommand, and full staged-options support for the South of Midnight
table (two-level cascade proof, staged-pending tap guard,
moAlwaysHideChildren pass-through + row-model subtree suppression); +24
tests, in-build suite 3,850 OK / 26 expected skips, `ce_inputs: []`;
previous 0.18
`native-20261028T131208Z-55922918` @ `70c5a61` - the trainer UI row-details
window; previous 0.17
`native-20261027T094839Z-ec6c6f55` @ `ee41630`;
previous 0.16.4 `native-20261024T003853Z-a8cf04fc` @ `988ff8e`,
previous 0.16.3 `native-20261023T065015Z-afbc3eba` @ `6a5ba63`, previous
0.16.2 `native-20261022T160328Z-0423fb21` @ `68eeb00`, previous
0.16.1 `native-20261021T161241Z-b0566a25` @ `d1c61f2`, previous
0.16 field-fix re-cut 2 `native-20261021T123801Z-8c5c4e1e` @ `108170b`,
re-cut 1 `native-20261020T150115Z-c426fb92` @ `7616edb` and first
0.16 run `native-20261020T103508Z-0e3f9d90` @ `809666a` superseded) with
the full Wave 4 feature set, RT-4.1 symbol provider fidelity (catalog
remeasure 2,698 -> 1,858 blocked of 117,624, zero unexplained supported
regressions), RT-4.4 value semantics (catalog remeasure
`blocked-catalog-rt44`: 1,858 -> 1,807 blocked of 117,634, zero newly
blocked rows) and the post-release field fixes (WP-58 UI
startup crash fix, Sinking City 2 activation-chain runtime evidence,
state-lock self-repair and reliable restart, SC2 startup-block
journal-field fix, SC2 activation field fix, SC2 crash-observability
field fix)
on top of the released 0.15 (prefix-cut field fix `d15268a`, part-3
fast-path fix `d068c44`); Wave 4 of the
reference-corpus closure cycle complete — all twelve W4 lanes
(WP-43/44/45/46p1/46p2/47/48/49/50/51/52/53/54/55/56/57 + WP-58 UI)
merged into `main` @ `0a38213`, cases 26/27/31 + 28/29/30 pinned
(30 pinned corpus tables, 6,143 AP-11 actions, weights
7,475/7,475 over run `w4b4-case30-20261020081722Z`); 0.9.0-rc2 was the
last user-tested release; `main` tracks the milestone between
releases):**
the
repository is a
self-contained, clean-room development base for an independently designed,
source/binary-redistributable converter and trainer with **no CE
implementation inputs or binaries at all**. It was formerly named
"TrainerForge (Native)"; use CT2Trainer in all current code,
configuration, documentation and tooling.

Read first: the [current status overview](STATUS.md), then the
[central gap & goal tracking document](plans/TRACKING.md)
(single source of truth for all open gaps, goals, work packages, corpus
cases and the latest measurement snapshot), then the active
[100% reference-table roadmap](plans/reference-table-100-roadmap.md) and the
[progress ledger](documentation/native-progress.md). They contain
the work packages, parallel ownership, resume commands and acceptance
criteria. The [earlier continuation plan](plans/archive/native-implementation-continuation.md)
preserves AP-01…AP-12 history. Code/build boundaries: `documentation/native-runtime.md` and
`documentation/native-verification.md`. Build guide:
`documentation/build.md`.

Native builds run exclusively with **`scripts/Build-Native.ps1`** (fully
offline, hash-verified inputs from `dependencies/`). Local MIT/BSD forks,
adaptations and upstream API breaks are authorized; retain source pins,
notices, local changes and build evidence.

**CE behavior reference (2026-10-13, user decision):** the Cheat Engine 7.5
source tree at `C:\Users\xboxl\code\cheat-engine-7.5` (local-only, never
added to git) may be **read** to understand how CE handles a behavior
(offset parsing, `{$…}` directives, `return:` label scoping, phase
splitting, duplicate-ID tolerance, …). It is a **lookup/reference source
only**: no CE code is copied, derived, or ported into CT2Trainer — every
feature is re-implemented clean-room, and public API/format contracts may
be derived. All other CE implementation sources remain off-limits.

**Feature-matrix goal:** 100% coverage without AP-11. 42/42 in-scope
features covered (100% feature-weighted; 7475/7475
action-weighted; `gap_inventory/feature-coverage.json`, run
`w4b4-case30-20261020081722Z`; the 2026-10-19 7446/7446 over
`w4-case31-20261019061339`, the 2026-10-18 7426/7426 over
`w3e-case24-20261018051230`, the 2026-10-18 7416/7416 over
`w3d-case22-20261018040510`, the 2026-10-18 7413/7413 over
`w3b-case21-20261018023823Z`, the 2026-10-18 7411/7411 over
`w3-case23-20261018012531Z`, the 2026-10-16 7408/7408 over
`w2b-case18-20261016142912Z`, the 2026-10-15 7387/7387 over
`w2c-case15p2b-20261015144326Z`, the 2026-10-14 7381/7381 over
`w2a-case17-20261014112532Z`, the 2026-10-14 7376/7376 over
`w1a-case15-20261014011543Z`, the 2026-10-14 7371/7371 over
`w1a-case16-20261014003107Z`, the 2026-10-13 7369/7369 over
`w1e-case20-20261013234642Z`, the 2026-10-13 7365/7365 over
`w1d-case19-20261013192913Z`, the 2026-10-11 7361/7361 over
`wp14-staged-20261011T093320Z` and the 2026-10-10 39/39 over
`wpB-cleanroom4-20261010T104008Z` are superseded). The 90% hurdle and the
100% goal are reached and closed. All three gate features are closed with **real,
tested** evidence (2026-10-10):

1. `gate:1` – per-table completeness for all 30 pinned tables
   (Forms, Lua lifecycle, Custom Types, Assets):
   `tests/test_native_table_completeness.py` (every source record
   preserved; each table-level construct handled or surfaced fail-closed;
   synthetic embedded-Files case).
2. `gate:2` – Source-to-Frozen parity of the 0.9 feature set
   (`tests/test_native_source_frozen_parity.py`) + binary CLI/GUI adapter
   for the static IL2CPP parser:
   `src/ct2trainer/native/il2cpp_static_probe.py`, frozen launcher flags
   `--il2cpp-static-pe/--il2cpp-static-metadata/--il2cpp-static-report`,
   source CLI `ct2trainer native il2cpp`
   (`tests/test_native_il2cpp_static_probe.py`).
3. `gate:3` – end-to-end reproducibility chain across all features with
   exact commands and pinned inputs:
   `tests/test_native_repro_chain.py` (denominator -> feature matrix ->
   AP-11 manifest, byte-identical per fixed run-id).

Gate flips happen only with **real, tested** evidence; gate action weights
remain 0 (completeness/proof features, not record actions). The AP-11
campaign (6143 expected actions, 0 confirmed so far) remains a
**separate end goal** and is excluded from the 100% feature metric.

**Corpus:** `TableReferences/` is the synthetic clean-room corpus
(`case-01.ct` … `case-14.ct`, `case-15.ct`, `case-16.ct`,
`case-17.ct`, `case-18.ct`, `case-19.ct`, `case-20.ct`,
`case-21.ct`, `case-22.ct`, `case-23.ct`, `case-24.ct`,
`case-26.ct`, `case-27.ct`, `case-28.ct`, `case-29.ct`,
`case-30.ct`, `case-31.ct`; case-to-origin
mapping in `TableReferences/README.md`). `case-14.ct` is the WP-14
PRAGMATA behaviour derivative (staged capabilities, signed offsets,
activation sets). It is strictly read-only input; distributed releases
never contain original game tables.

**Versioning rule (2026-10-21, user decision):** every build gets a
new version number. Feature releases bump the minor (0.16 → 0.17);
bug-fix builds bump the patch (0.16 → 0.16.1 → 0.16.2). Bump the root
`VERSION` file in the same change as the content change that triggers
the build, and add a `CHANGELOG.md` entry per shipped version.

**Distributed-release naming:** fresh builds produce
`CT2Trainer-<version>-source.zip` and
`CT2Trainer-<version>-windows-portable.zip` (version = content of the
root `VERSION` file); the binary plan footer magic is `CT2NATV1` and the
template stub marker is `CT2BASE1` (both 8 bytes). `TFSH0001` (one-shot
marker magic in `oneshot.json`, `one_shot_contract.py`) is intentionally
kept as a stable format constant — renaming would break existing user
state; it is documented, not a naming-debt item.

The build allowlist in `tools/native_build.py` (`source_files()` /
`RELEASE_DOC_FILES`) is the single source of truth for release content and
is verified by the in-build CE-content scan. Agent tooling (`AGENTS.md`,
`plans/`, `tools/agent_load.py` and the agent docs under `documentation/`)
is local-only by design and excluded from distributed ZIPs.

**Latest verified build:** `native-20261108T100731Z-a1d311e5` (0.32,
cut from `main` @ `bfcc3a3`, 2026-11-08; in-build suite 4,483 OK / 30
expected skips, `ce_inputs: []`, `runtime_unverified` deliberately
kept per gate; source ZIP `CT2Trainer-0.32-source.zip` sha256
`f6cae57590d083e37308bc4a03b1046b8186617bdb0f98c88c9bc324404493d9`
(14,426,224 bytes) - carries the MT-24 Entries / Blocked columns,
`table_analysis.py` + `analysis_worker.py` (incl. the
`active_workers()` live-worker registry), the mt23 worker-guard
test fix and the reviewable `master_trainer/UI.md` - and portable
ZIP `CT2Trainer-0.32-windows-portable.zip` sha256
`3a7980ba04f60f7cb93edce3cf5c723ba609ff55a00b1f866079101d3b7bc986`
(49,699,633 bytes; the frozen `CT2Trainer-Master.exe`
(sha256 `6dc34408c8e5ecec1c2215c45da27ea22cc5c5ce5a9629267778b172d44d3485`,
16,966,114 bytes) ships next to the converter)).
0.32 ships the Master Trainer per-table entry count + blocked
count via background plan analysis (MT-24). Superseded 0.31 build:
`native-20261105T080853Z-2e7f50a5` (0.31,
cut from `main` @ `2def12f`, 2026-11-05; in-build suite 4,414 OK / 30
expected skips, `ce_inputs: []`, `runtime_unverified` deliberately
kept per gate; source ZIP `CT2Trainer-0.31-source.zip` sha256
`3bab9648208f6ed4cbafa919991cab19c7921597ac2075c5c8b964e17258c0f9`
(14,398,817 bytes) - carries the MT-23 per-table live status +
color coding + status filter and the reviewable
`master_trainer/UI.md` - and portable ZIP
`CT2Trainer-0.31-windows-portable.zip` sha256
`df5581ec5e8b0c0b99abdf35b914f08ec138b4470234b48c615304419a970839`
(49,679,202 bytes; the frozen `CT2Trainer-Master.exe`
(sha256 `811c0f85c143b632dd182646282ddb32c3293513a665eb62c8055f74f9c89dcb`,
16,948,380 bytes) ships next to the converter)).
0.31 ships the Master Trainer per-table live status + color
coding + status filter (MT-23). Superseded 0.30 build:
`native-20261104T131114Z-11522f68` (0.30,
cut from `main` @ `2fbca94`, 2026-11-04; in-build suite 4,386 OK / 30
expected skips, `ce_inputs: []`, `runtime_unverified` deliberately
kept per gate; source ZIP `CT2Trainer-0.30-source.zip` sha256
`091b379c132e277c19f519705dcccc4c0817e8e7e614e5baf2f14bbe3fe414a3`
(14,387,690 bytes) - carries the MT-22 table details +
load-gate preview and the reviewable `master_trainer/UI.md` - and
portable ZIP `CT2Trainer-0.30-windows-portable.zip` sha256
`f4476bb08e3e65e6db9cd35bfe7a72408a555b8525bd6a10f8b794f943083d54`
(49,669,933 bytes; the frozen `CT2Trainer-Master.exe`
(sha256 `9d0a525a78dfbfffb906261ad42e435c5414cb6cb0189dd78c73910063f67643`,
16,940,058 bytes) ships next to the converter)).
0.30 ships the Master Trainer table details + live load-gate
preview (MT-22). Superseded 0.29 build:
`native-20261104T094808Z-50af0517` (0.29,
cut from `main` @ `de3e4ff`, 2026-11-04; in-build suite 4,370 OK / 30
expected skips, `ce_inputs: []`, `runtime_unverified` deliberately
kept per gate; source ZIP `CT2Trainer-0.29-source.zip` sha256
`2f5ce6e446f8d9885cd653580b5e194a2a0fc524eba7b5f684fe1f1a0e1da3d4`
(14,378,934 bytes) - carries the MT-19/20 trainer-focus +
discoverability and the reviewable `master_trainer/UI.md` - and
portable ZIP `CT2Trainer-0.29-windows-portable.zip` sha256
`98c63c368bc2cccd68335e9db94a3b897abbbb815730c97912e3068805fad226`
(49,667,528 bytes; the frozen `CT2Trainer-Master.exe`
(sha256 `88e6ee99aa4c46973945e462ca956977e9942a1e8b30630aa2570107540f2de8`,
16,937,063 bytes) ships next to the converter)).
Superseded 0.28 build:
`native-20261103T161621Z-ea8fde2f` (0.28,
cut from `main` @ `d7f4cf0`, 2026-11-03; in-build suite 4,357 OK / 30
expected skips, `ce_inputs: []`, `runtime_unverified` deliberately
kept per gate; source ZIP `CT2Trainer-0.28-source.zip` sha256
`13f4b2222a83f9e4588d388b4120beaf8018a091a05364029ae2a950c0dabb1a`
(14,363,765 bytes) - carries the MT-18 pinned tables - and
portable ZIP `CT2Trainer-0.28-windows-portable.zip` sha256
`d656835a69ece75ff6adaa5ce766385327fb9ec08d89837ad772425dafe91ce3`
(49,658,473 bytes; the frozen `CT2Trainer-Master.exe`
(sha256 `c12dcea5bb8a609dae4df36f44827ab5269c9e1015cb723067ed98dc100bf99b`,
16,929,732 bytes) ships next to the converter)).
0.28 ships the Master Trainer pinned/favorite tables (MT-18).
Superseded 0.27 build: `native-20261103T145543Z-b29b3688` (0.27,
cut from `main` @ `8aa0815`, 2026-11-03; in-build suite 4,342 OK / 30
expected skips, `ce_inputs: []`, `runtime_unverified` deliberately
kept per gate; source ZIP `CT2Trainer-0.27-source.zip` sha256
`264b42d6c42dac1bb434c1d0591e82ac0bec69e61e1a1c75047c6aa58126f40e`
(14,357,294 bytes) - carries the MT-16/17 waiting-view settings and
the process groups - and portable ZIP
`CT2Trainer-0.27-windows-portable.zip` sha256
`bfcf2abc885122dfa8653fcfd0046323e7112f59c0850958688e36e014ebc135`
(49,654,613 bytes; the frozen `CT2Trainer-Master.exe`
(sha256 `9762c8bdc2298c16bd82779f206d9a885a449261a6428187c3bd2155fc5bf1bc`,
16,929,639 bytes) ships next to the converter)).
0.27 ships the Master Trainer waiting-view settings persistence
(MT-16) and the process-grouped waiting view (MT-17). Superseded
0.26 build: `native-20261103T112811Z-59a6b3d5` (0.26,
cut from `main` @ `c114ec2`, 2026-11-03; in-build suite 4,320 OK / 30
expected skips, `ce_inputs: []`, `runtime_unverified` deliberately
kept per gate; source ZIP `CT2Trainer-0.26-source.zip` sha256
`3d62f80cdfb95d8439d4a2f2150002976795faad313fa75d47aeb4fb92bb49bd`
(14,348,462 bytes) - carries the MT-13/14/15 waiting-view usability
and the live-target takeover field fix - and portable ZIP
`CT2Trainer-0.26-windows-portable.zip` sha256
`49be1d286999ed175737edb073c5ab83533c40cccc7e636685a256a0b07004b3`
(49,653,968 bytes; the frozen `CT2Trainer-Master.exe`
(sha256 `895f937ed5c228c09b97edba28aa9dc4ad228abd58585f73080f40ab265bc031`,
16,925,677 bytes) ships next to the converter)).
0.26 ships the Master Trainer waiting-view usability
(MT-13/14/15) and the live-target takeover field fix.
Superseded 0.25 build: `native-20261103T062439Z-f4c16be9` (0.25,
cut from `main` @ `a861bfb`, 2026-11-03; in-build suite 4,259 OK / 30
expected skips, `ce_inputs: []`, `runtime_unverified` deliberately
kept per gate; source ZIP `CT2Trainer-0.25-source.zip` sha256
`64f8c3082cff50687b1962234c17a82e2a2f0c19eb1112ece06a0a25132f35be`
(14,324,774 bytes) - carries the MT-10/11/12 user control,
`trainer_sounds.py`, the `test_native_master_*` / attach-pause test
files, and the final 0.25 changelog entry - and portable ZIP
`CT2Trainer-0.25-windows-portable.zip` sha256
`774266f7e2c9dc69f4d8cfc963309b9907442ec6b5343ff629b9e30c04049653`
(49,633,196 bytes; the frozen `CT2Trainer-Master.exe`
(sha256 `8736f73e762b57a8f337bf8fa04c2c16f8622c4d99e7dd7f2167b2c9999e3d8f`,
16,912,561 bytes) ships next to the converter)).
0.25 ships the Master Trainer user control (MT-10/11/12), the online
feature evaluation record, the Tcl test-harness hardening, and the
in-build reliability fix. The tick sounds remain untested on a live
game session (field test pending). Superseded 0.24 build:
`native-20261102T102029Z-fe358e35` (0.24, cut from `main` @ `a2777ed`,
2026-11-02): the trainer tick sounds release (clean-room in-code tick
synthesis for on/off/attach; in-build suite 4,193 OK / 30 expected
skips; source ZIP sha256
`dfdd8cfcca90a2789bf544d8f8de4e34941067feeb2b32ce8d550f98e5bc4eb6`,
portable ZIP sha256
`12262cf16e906c3811ade0a8c582b7a1057c834a3110aff004dfd13b3067e7ab`).
Superseded 0.23 build: `native-20261101T145310Z-a160bae4` (0.23,
cut from `main` @ `6e3ec98`; in-build suite 4,176 OK / 30 expected
skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per
gate; source ZIP `CT2Trainer-0.23-source.zip` sha256
`3360cab031cb1334dda71bb02a511170a9a70d1f583b5a8721624f46e24da464`
(14,291,040 bytes) - carries the `master_trainer` subpackage incl.
`table_gate.py`, the MT-9 test file, the placeholder-heading + SC2
hotkey-bridge field-fix test files and the final 0.23 changelog
entry - and portable ZIP
`CT2Trainer-0.23-windows-portable.zip` sha256
`eec023ba09e8fcb80608736896f0477f4a783034046e6ad67514e96ed0a2905b`
(49,609,916 bytes; the frozen `CT2Trainer-Master.exe`
(sha256 `e5822f688c653242a9f64bd92e4ba92529d485b89c11607cf20d32e728ca3c20`,
16,895,048 bytes) ships next to the converter)).
0.23 ships the full Master Trainer roadmap (MT-6/MT-7/MT-8/MT-9,
waiting-view observability, ask-on-first-start folder parameter)
plus the same-day field fixes (placeholder-heading symbol-
dependency skip, SC2 hotkey-bridge field fix from the 0.22.1 lane).
Superseded 0.22 build: `native-20261101T075049Z-f32c112d` (0.22,
cut from `main` @ `2b24a1c`; in-build suite 4,061 OK / 30 expected
skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per
gate; source ZIP `CT2Trainer-0.22-source.zip` sha256
`c5db1b92c8851d4937e2544a77bd0787c5d48c941ebcfef8741cf4ae104ac7cf`
(14,243,974 bytes) - carries `tests/test_native_rearm.py` and the 0.22
changelog entry - and portable ZIP
`CT2Trainer-0.22-windows-portable.zip` sha256
`f89cd0225b5d439bf18106728c3a89e906e56957fd28b9b7b2b5e16f5c3c221a`
(33,023,506 bytes)).
0.22 ships the FO4 field-fix cycle (bounded automatic re-arm of
ScanMiss enable failures, 30 s x 10 attempts, budget reset per
(re-)attach, armed set survives target exit + manual Try again /
Re-attach actions; The Sinking City 2 0.19 hotkey-bridge field
findings are recorded in the ledger - the fix itself ships in 0.23
via the 0.22.1 lane). Superseded 0.21 build: `native-20261031T211046Z-14707e12` (0.21,
cut from `main` @ `9a725a8`; in-build suite 4,044 OK / 30 expected
skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per
gate; source ZIP `CT2Trainer-0.21-source.zip` sha256
`9dacb4093cd8a7f0444fed9ed7ae9aed6f82c14132ee4f3197b1fb5747580a13`
(14,231,850 bytes), portable ZIP
`CT2Trainer-0.21-windows-portable.zip` sha256
`0701d507701cb2952e1e35e1357bac4b459b38fe87e6811b6b272f2a2c3acaaa`
(33,010,077 bytes)).
0.21 ships RT-5 complete (item B CheatCodes code-patch plan path,
item E messageDialog safe logged no-op; catalog remeasure
`blocked-catalog-020-rt5-be`: 117,809 total / 116,756 supported /
1,053 blocked, +175 supported, zero newly blocked) plus the new
Master Trainer (MT-1..MT-5: incremental folder table index,
cross-platform process watch, auto-load / picker, handoff into the
exact standalone trainer UI, per-table on/off persistence; 141 tests,
zero catalog effect); the source ZIP carries the `master_trainer`
subpackage, the 4 master test files and the `Master_Trainer` icon
assets. Superseded 0.20.1 build: `native-20261031T104114Z-d64ae4c2`
(0.20.1, cut from `main` @ `080128c`; in-build suite 3854 OK / 26
expected skips, `ce_inputs: []`, `runtime_unverified` deliberately
kept per gate; source ZIP `CT2Trainer-0.20.1-source.zip` sha256
`d6ced6ee91fbdd7f12ea4bd6dae92fe49ecf83691c01a867c11279b8f67fb335`
(13,326,889 bytes), portable ZIP
`CT2Trainer-0.20.1-windows-portable.zip` sha256
`c8f022b1facec2d3457789a24d2f31583ad9108ee9689148f19615a53d2a31c6`
(31,313,979 bytes)).
0.20.1 re-cuts the 0.20 branding-icon release with the corrected 0.20
changelog suite line (verified in-build suite at the canonical path)
and the cited catalog remeasure `blocked-catalog-020-icons` (zero delta
vs `blocked-catalog-019-field`); no code or asset changes. Superseded
0.20 build: `native-20261030T184820Z-b9d6dc07` (0.20, cut from `main` @
`6298803`; source ZIP `CT2Trainer-0.20-source.zip` sha256
`9ca6dca67b5f7316d8be29b7bab07fa702c9551430f9193c6bf647d052d3ffe3`
(13,326,708 bytes), portable ZIP
`CT2Trainer-0.20-windows-portable.zip` sha256
`bddaed809f9771338eac03ed9cb8536f1df6bde23aac0e14cc43009fc61e554a`
(31,313,518 bytes)): the user-provided branding icons - the
`CT2Trainer_Generator` set on the tool EXE (PyInstaller `--icon` +
`window_icon_path("converter")`) and the `Standalone_Trainer` set
embedded in the `CT2Trainer-Template` stub so every generated trainer
carries it (`window_icon_path("trainer")`); 1024x1024 PNG masters
committed, multi-size ICOs (16-256 px, 32 bpp) rebuilt by the rewritten
`tools/create_icons.py`, `tests/test_native_icons.py` +4; both frozen
EXEs verified to carry the new icon resources (largest embedded RT_ICON
blob byte-identical to the committed ICO's 256-px entry); the first
0.20 cut (`native-20261030T183527Z-8f2cb20a`) was cut from the wrong
branch (duplicate 0.19 ZIPs without icons) and deleted before
recording. Superseded 0.19 build: `native-20261030T121918Z-c72dbb38`
(0.19, cut from `main` @ `fbe626f`; in-build suite 3850 OK / 26
expected skips, `ce_inputs: []`, `runtime_unverified` deliberately kept
per gate; source ZIP `CT2Trainer-0.19-source.zip` sha256
`3eaa6a987e820477955fe84e77ed089527e3199705b81409fad8b1139aab258d`
(13,243,532 bytes), portable ZIP
`CT2Trainer-0.19-windows-portable.zip` sha256
`a440051c0d10eb434cb0bf76799092729fe5a54b06fdc38a13ede84b4a4ae4c4`
(28,800,949 bytes)).
0.19 ships the field-fix cycle from the 0.18 field tests: the
Sinking City 2 hotkey-bridge Windows AV fix (HWND_MESSAGE corrected
to -3, explicit Win32 argtypes/restype on all bridge prototypes,
guarded RegisterHotKeyW/UnregisterHotKeyW for stripped user32
builds, `run_trainer` hotkey-bridge-started/-failed events,
`tests/test_native_os_hotkeys.py` +1 real-seam regression test),
value-read observability (`read_value` logs `value-read-failed` per
identifier per cause, dedup, re-raise), the new `describe` CLI
subcommand (`ct2trainer native describe`, +13 tests in
`tests/test_native_describe.py`), and full staged-options support for
the South of Midnight table (plan-level staging, engine gates and the
two-level parent cascade proven by `tests/test_native_staged_cascade.py`
+2; UI gaps closed - staged-pending tap guard routing the tap through
`engine.read_value` so the named staged refusal lands in the status
line, and `moAlwaysHideChildren` pass-through as the `hidden_children`
plan marker with row-model subtree suppression keeping the flagged
parent row; `tests/test_native_staged_options_ui.py` +8) on top of
the 0.18 content. Catalog remeasure `blocked-catalog-019-field`:
zero delta vs `blocked-catalog-rt5d-main` (1,053 blocked of 117,634,
60,161 staged, 0 load errors). Superseded 0.18 build:
`native-20261028T131208Z-55922918` (0.18,
cut from `main` @ `70c5a61`; in-build suite 3767 OK / 25 regular
skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per
gate; source ZIP `CT2Trainer-0.18-source.zip` sha256
`3d8612ed97dbfb80a4c4fc95f9899852285ac184a738a03932bc9fad240ed967`
(13,190,182 bytes), portable ZIP
`CT2Trainer-0.18-windows-portable.zip` sha256
`9e4080e07b33f3b2a3a97178891916b711955b96f9b0fa6139a6b120fea3b9ca`
(28,740,039 bytes)).
0.18 ships the trainer UI row-details window (right-click / long-press
on a row offers "Row details" leading the context menu - one read-only
window with the raw script source, the plain-language assessment and
the concrete actions the trainer performs per entry; new pure builders
`entry_actions` / `row_details` / `lua_apis_used` in
`ui_script_view.py`, +22 tests in `tests/test_native_ui_row_details.py`)
on top of the 0.17 content. Superseded 0.17 build:
`native-20261027T094839Z-ec6c6f55` (0.17, cut from `main` @ `ee41630`;
in-build suite 3692 OK / 25 regular skips, `ce_inputs: []`,
`runtime_unverified` deliberately kept per gate; source ZIP
`CT2Trainer-0.17-source.zip` sha256
`08af7d402df6380713f75cd270a27b9eb512e78a173d169ebd142f9411e65eee`
(13,162,166 bytes), portable ZIP
`CT2Trainer-0.17-windows-portable.zip` sha256
`ee6ad2ec4b72705b6a48f6631343c4caef1056f7bca5400ec0c5ebd8159ac15a`
(28,710,096 bytes)).
0.17 ships the RT-4.2 runtime provider model (last RT-4 package;
catalog remeasure `blocked-catalog-rt42-main`: 1,351 -> 1,053
blocked, 298 rows unblocked, zero newly blocked, 28 reason-only
changes) plus the RT-4.3 address-expression & identifier-dialect
merge, the RT-4.5 and RT-4.6 merges, the trainer UI Scripts view and
row context menu, and the RT-5 item G / F gate ratifications, on top
of the 0.16.4 content. Superseded 0.16.4 build: the
Sinking City 2 trainer-crash-observability field fix
(0.16.3 field test 2026-10-23: the windowed trainer process died
silently mid wish-restore - last event the TALENTPTR aobscan at
18:49:31, zero follow-up events - and the restart was blocked by the
correct state-lock refusal while the game was still running; every
Python-level failure path logs an event, so the silent death is a hard
exit, and the windowed build had no crash observability at all:
unattached stderr, no excepthook/faulthandler, unguarded Tk poll
callback) - `TrainerDebugLog.arm_crash_reporting()` installs one-time
process-wide `sys.excepthook` (`trainer-crashed` JSON event with full
traceback) and `threading.excepthook` (`trainer-thread-crashed`)
wrappers plus `faulthandler` on a dedicated append handle independent
of `close()`, `run_trainer` arms both entry points,
`TrainerWindow.poll` wraps `engine.poll()` fail-closed
(`poll-crashed` + engine block + tick continues), and the restore loop
logs `restore-entry-start` per wish before enable; state-lock
fail-closed behavior unchanged; regression test
`tests/test_native_sc2_crash_observability.py` +8) on top of the
0.16.3 content and the RT-4.4 value-semantics merge (catalog remeasure
`blocked-catalog-rt44`: 1,858 -> 1,807 blocked of 117,634, zero newly
blocked rows). Superseded 0.16.3 build:
`native-20261023T065015Z-afbc3eba` (0.16.3, cut from `main` @ `6a5ba63`;
in-build suite 3421 OK / 25 regular skips, `ce_inputs: []`,
`runtime_unverified` deliberately kept per gate; source ZIP
`CT2Trainer-0.16.3-source.zip` sha256
`0b34c4f3797095aefcba66a45d46216596e816817ea1b98208a42a5217df2e5a`
(13,050,549 bytes), portable ZIP
`CT2Trainer-0.16.3-windows-portable.zip` sha256
`bb495a6f61538051b8caeac14394bdc80b7b165b946f34f3ae710524e37fd0a3`
(28,609,768 bytes)).
0.16.3 ships the Sinking City 2 activation field fix (0.16.2 field
test 2026-10-22: the recovery assessment still rejected the WP-47/55
hook-journal `value_data_ranges` field on every allocation entry,
blocking startup behind a stale `state.lock` on every attempt; and
the module-snapshot retry targeted the wrong Win32 code -
`ERROR_BAD_LENGTH` mislabeled as 24, real 1116; 24 is
ERROR_INVALID_ID, the transient code observed 9 ms after attach while
the game was still loading DLLs; now a bounded 8-attempt
exponential-backoff retry on {1116, 24, 119}, architecture-aware
native-only fallback flag (0x10 for 32-bit targets), dual-failure
message carrying both codes; regression tests
`tests/test_native_architecture.py` +4 and
`tests/test_native_recovery.py` +2) on top of the 0.16.2 content.
Superseded 0.16.2 build:
`native-20261022T160328Z-0423fb21` (0.16.2, cut from `main` @
`68eeb00`; in-build suite 3415 OK / 25 regular skips, `ce_inputs:
[]`, user-tested, field finding: Sinking City 2 activation failure) -
the Sinking City 2 startup-block field fix (recovery assessment
accepts the WP-57 hook-journal `captured_placeholders` field;
regression tests `tests/test_native_recovery.py`) and RT-4.1 symbol
provider fidelity (keep-first duplicate-provider policy, `label()`
duplicate-name tolerance, wildcard-cleanup scoping; catalog remeasure
2,698 -> 1,858 blocked of 117,624, zero unexplained supported
regressions) on top of the 0.16.1 content. Superseded 0.16.1 build:
`native-20261021T161241Z-b0566a25` (0.16.1, first build under the new
versioning rule, cut from `main` @ `d1c61f2`; in-build suite 3412 OK /
25 regular skips, `ce_inputs: []`, user-tested, field finding: Sinking
City 2 startup block) — Sinking City 2 table-load warning fixes
(table-version reference 45 → 46 field-verified; `{$LUA}` warning
states the built-in Lua runtime path; external-action warning split
per API — ShellExecute safe no-op, messageDialog review flag) on top
of the 0.16 content, regression tests
`tests/test_native_sc2_table_warnings.py`.
0.16 ships the full Wave 4 feature set (WP-43…WP-57 + WP-58 UI, see
changelog) plus the post-release field fixes on top of the released 0.15
content (WP-58 UI startup crash: `_button` widget defaults merged into
the style dict + pagination tuple `padx` moved to `.pack()`, regression
test `tests/test_native_ui_button.py`; Sinking City 2 activation-chain
runtime evidence `tests/test_native_sc2_attach_chain.py`; state-lock
self-repair and reliable restart: close-after-blocked exit cleanup when
the target is gone, atexit session/lock release on a provably gone
target, actionable stale-lock refusal with assessment reasons and one
probe retry, regression tests
`tests/test_native_stale_lock_selfheal.py`); 30 pinned corpus tables,
6,143 AP-11 actions, weights 7,475/7,475 over run
`w4b4-case30-20261020081722Z`; both ZIPs carry the changelog with the
0.16 + 0.15 + 0.14 entries. Superseded 0.16 runs:
`native-20261021T141051Z-17d53c1d` (0.16, cut from `main` @ `e9f06fb`
after the RT-1 rebaseline; in-build suite 3405 OK / 25 regular skips,
`ce_inputs: []`; superseded by the 0.16.1 cut before its evidence was
recorded); `native-20261021T123801Z-8c5c4e1e` (0.16 field-fix re-cut 2,
cut from `main` @ `108170b`; in-build suite 3405 OK / 25 regular
skips, `ce_inputs: []`; user-tested, field finding: Sinking City 2
table-load warnings); `native-20261020T150115Z-c426fb92` (0.16 field-fix re-cut, cut from
`main` @ `7616edb`; in-build suite 3398 OK / 25 regular skips,
`ce_inputs: []`; source ZIP sha256
`35717144ed8c74fb1c690c8e692a0d53225b86401190b524715559bc13577ade`,
portable ZIP sha256
`24050f691603981ff0c33e2550adc885581a5131cd5a8123d0050618ca18178d`;
user-tested, field findings: one cheat = table/build mismatch, state-lock
orphan after a blocked close) and `native-20261020T103508Z-0e3f9d90`
(0.16, cut from `main` @ `809666a`; in-build suite 3393 OK / 25 regular
skips, `ce_inputs: []`; source ZIP
sha256 `370a2d73c597de283e4b0db9a7c5c8d68d542fba6d9516d9314c2bfc9cb1118e`,
portable ZIP sha256
`6db5bf69052767cf07529458c45d3f1c5f5089e8934c74ef2ce053b27dd23b8b`;
user-tested, shipped with the WP-58 UI startup crash). Previous release
build:
`native-20261018T055505Z-39f20180` (0.15, cut from `main` @ `ed0b97b`;
in-build suite 3057 OK / 25 regular skips, `ce_inputs: []`,
`runtime_unverified` deliberately kept per gate; source ZIP
`CT2Trainer-0.15-source.zip` sha256
`5d5a85f63f0b0948b05e06bfba8f40fa91e7bf75e5d981da22b33a3a5f522581`,
portable ZIP `CT2Trainer-0.15-windows-portable.zip` sha256
`cfcc8e06f65d0b3c6ec1ef4671f2be520c45c1c6c85572f1dbe6e69d15ea8414`).
The 0.15 build adds the prefix-cut byte-patch validation (the
0.14-ext2 Great Circle field fix: `db 90 E9` over a 6-byte conditional
jump is now proven against the live target at link time and re-verified
at stage time, restoring the Stealth Mode and No Reload entries) and
the full Wave 3 feature set (per-record hotkeys, creator per-table
inspection, runtime dynamic address providers, read-only table-Lua
bootstrap with trainer banner, Lua-owned symbol handover with
teardown-order invariants) on top of the released 0.14 content; 24
pinned corpus tables, 6,100 AP-11 actions, weights 7,426/7,426 over
run `w3e-case24-20261018051230`; both ZIPs ship the elaborated release
READMEs (source: product overview + build guide; portable: full user
guide, including the debug-logging section) and the changelog with the
0.15 + 0.14 + 0.13 entries. Previous release build:
`native-20261017T115850Z-1ebb48b7` (0.14, cut from `main` @ `fca6b06`;
in-build suite 2932 OK / 25 regular skips; source ZIP sha256
`a5b075cf6535c5eef3807da7b7b9429dda08a3cf9f9dba6fdafb879e0dfce0a9`,
portable ZIP sha256
`e57fe9b9fb56ef7a97f81a98f04455976c4b5e9ebddee655b24cbb64e7ed3103`).
Earlier release build: `native-20261016T190005Z-b3139b30` (0.13, cut from
`main` @ `d57e62c`; in-build suite 2927 OK / 25 regular skips; source
ZIP sha256
`23b57307819e4262d8ca894ac16c86d595df9945c1afec25750f66bb9e0c9124`,
portable ZIP sha256
`d7f64efbae975f477e5bb011796d64276f32ef4300d4a0986961e95ae63aca78`).
Superseded 0.13 run: `native-20261016T181516Z-b8ae88de` (pre
module-snapshot fallback, cut from `main` @ `7184547`). Prior
release build: `native-20261016T163910Z-d047f2d2` (0.12, cut from
`main` @ `ba1d3e4`;
in-build suite 2910 OK / 25 regular skips; source ZIP sha256
`f5a5468da6e49ee5d4812dce3edea71e87e4bb9736ce4bf3486dfc0c66e70165`,
portable ZIP sha256
`7bd582e33f2978c641bb36a22ad8fc5f21bc9b695bb16930bed19720eaa81619`),
which contains the full Wave 2 set: W2-A (WP-27/32/33/34, merge
`aa6371b`), W2-C (WP-30/36, merge `32e0cdd`) and W2-B
(WP-28/29/31/35, merge `2f68f80`). Superseded 0.12 runs:
`native-20261016T161905Z-e8ef67a0` (byte-identical re-cut of the final
tree) and `native-20261016T154141Z-2de774ab` (pre release-docs update).
Superseded 0.11 run:
`native-20261012T092729Z-2d8aaf12` (0.11, cut from `main` @ `9a76eb8`;
in-build suite 2710 OK / 25 regular skips; source ZIP sha256
`168c14a452595588a6483140f1d43bec818d0f0d0e9eb72167453a80624469db`,
portable ZIP sha256
`8a2d6ac6f8b802714fe7578de54cea432506a41f8bf91d597a03fa086b04f196`).
Previous: `native-20261011T121914Z-bfc5fc11` (0.10, full WP-14 work,
in-build suite 2671 OK / 25 regular skips);
`native-20261010T172336Z-ffe35eb0` (0.9.0-rc2, in-build suite
2617 OK / 25 regular skips) was user-tested on a machine without CE or
Python (converter run plus generated trainer).

Workflow policy: each implementation cycle (milestone 0.9 and beyond)
runs on its own working branch (e.g. `native-0.9`); within a cycle, after
each integrated work package (or batch of lane integrations including
matrix flips and docs), the working branch is merged into `main` and
pushed again (normal merge + push, never force), so `main` continuously
tracks the milestone between cycle-end releases. `main` receives only
these release merges.

Subagent launch rule: before starting any new subagent lane, check the
model-server load with `tools/agent_load.py` (sglang metrics endpoint;
exit 0 = at least one lane may launch, 1 = defer). Launch new agents only
when the request queue is empty, the free KV span is substantial and the
abort counter is flat; under high load defer launches and advance
root-owned work in the meantime. Parallelize lanes up to the actual
capacity of the server so the available resources are used optimally;
never blindly launch into a saturated server. Lane contract:
`documentation/subagent-lane-rules.md`.

Read before any change:

1. [`README.md`](README.md) — quick start, provenance and current scope.
2. [`plans/reference-table-100-roadmap.md`](plans/reference-table-100-roadmap.md) — active RT-1…RT-7 work packages and acceptance.
3. [`documentation/native-progress.md`](documentation/native-progress.md) — confirmed base, measured numbers and prioritized work.
4. [`documentation/native-runtime.md`](documentation/native-runtime.md) / [`native-verification.md`](documentation/native-verification.md) — code/build boundaries and proofs.
5. [`documentation/build.md`](documentation/build.md) — offline build, local test suite, release content rules.
6. [`documentation/native-semantic-denominator.md`](documentation/native-semantic-denominator.md) — pinned corpus tables and gap classes.
7. [`tests/deck/compatibility-matrix.md`](tests/deck/compatibility-matrix.md) — Proton/Steam Deck protocol, and [`tests/windows/fixture_target/README.md`](tests/windows/fixture_target/README.md) — the own Windows test target process.
8. [`documentation/subagent-lane-rules.md`](documentation/subagent-lane-rules.md) — parallel lane rules.

Confirmed product path: required inputs are a `.CT` file and the exact
game process EXE name; private own use. Saved enabled toggles are
automatically re-enabled after a successful re-attach. Only confirmed
ON-switches are persisted; a failed enable attempt stays visibly inactive
and is not repeated as a saved wish on the next attach. Final acceptance
is separate on Windows and on a real Steam Deck under Proton with touch
operation.

After new Windows or Deck tests, record the observed build — including
versions, hashes, test setup and result — in the documentation before
raising the status. Original-table Lua and Auto Assembler code may
execute when a generated trainer runs against its target; the local
tooling (converter, tests, corpus analysis) does not execute it.
