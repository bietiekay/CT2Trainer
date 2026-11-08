# CT2Trainer: where we stand

**Updated:** 2026-11-06. **0.32 content on main (build cut pending)**
- the 0.32 build is cut from this content; 0.31 remains the latest
verified release (build `native-20261105T080853Z-2e7f50a5`, cut from
`main` @ `2def12f`, 2026-11-05) - Master Trainer per-table entry
count + blocked count via background plan analysis MT-24 (the
waiting-view Entries / Blocked columns - the actionable and blocked
record counts of the plan compile, computed in one background daemon
thread through the tested `compile_table` plan path, persisted in
`table-analysis.json` keyed by the table content sha256 with an
LRU cap; the meta line shows the live "analyzing N table(s)" figure;
the details window gains the analysis block; a named compile failure
shows the failed marker); +69 tests; full main suite 4,483 OK / 30
expected skips; catalog zero delta
`blocked-catalog-032-analysis`; see the 0.32 section below.
Superseded 0.31 (build
`native-20261105T080853Z-2e7f50a5`, cut from `main` @ `2def12f`,
2026-11-05) - Master Trainer per-table live status +
color coding + status filter MT-23 (the waiting-view Status column
shows the table's state right now - one bounded stat per visible row
per render against the index entry: ok / running / changed / missing
/ unreadable; row color coding; the persisted "Status: all / ok /
attention" header cycle, master-state schema 5 -> 6, `view_status`;
the pure `table_status.py` decision layer); +28 tests; full main
suite 4,414 OK / 30 expected skips; catalog zero delta
`blocked-catalog-031-status`; see the 0.31 section below.
Superseded 0.30 (build `native-20261104T131114Z-11522f68`, cut from
`main` @ `2fbca94`, 2026-11-04) - Master Trainer table details +
live load-gate preview MT-22 (right-clicking a waiting-view row
offers "Table details" first - the read-only inspection window with
the indexed facts for the table plus the on-demand load-gate
re-check, the same pass MT-9 runs at load time; the pure
`table_details.py` row builder); +16 tests; full main suite 4,386 OK
/ 30 expected skips; catalog zero delta `blocked-catalog-030-details`;
see the 0.30 section below. Superseded 0.29 (build
`native-20261104T094808Z-50af0517`, cut from `main` @ `de3e4ff`,
2026-11-04) - Master Trainer UI/UX revamp MT-19/20 (MT-19
trainer-focus mode: the whole waiting view lives in one container
frame destroyed on trainer entry - the trainer row grid owns the
full window, rebuilt whole on the way back; MT-20 discoverability:
the read-only "UI flow" header button - the in-app copy of the
reviewable UI.md, F5 re-scan, initial table-list focus, "Retry
load" in the status bar); +13 tests; full main suite 4,370 OK / 30
expected skips; catalog zero delta
`blocked-catalog-029-trainer-focus`; see the 0.29 section below.
Superseded 0.28 (build `native-20261103T161621Z-ea8fde2f`, cut from
`main` @ `d7f4cf0`, 2026-11-03) - Master Trainer
pinned/favorite tables MT-18 (`master-settings.json` schema 4 → 5:
the pin set - relative paths, most recent pin first, cap 25 -
persisted and restored at start; the row context menu toggle,
pinned tables float to the top of the list view and to the top of
their process group, the pin marker in the detail column); +15
tests; full main suite 4,357 OK / 30 expected skips; catalog zero
delta `blocked-catalog-028-pin`; see the 0.28 section below.
Superseded 0.27 (build `native-20261103T145543Z-b29b3688`, cut from
`main` @ `8aa0815`, 2026-11-03) - Master Trainer waiting-view
settings persistence MT-16 (`master-settings.json` schema 3 → 4:
the filter query, sort mode and view mode restored at start and
persisted on every change) + the process-grouped waiting view MT-17
(group-by-bound-process tree, display-only group rows); +22 tests;
full main suite 4,342 OK / 30 expected skips; catalog zero delta
`blocked-catalog-027-view`; see the 0.27 section below.
Superseded 0.26 (build `native-20261103T112811Z-59a6b3d5`, cut from
`main` @ `c114ec2`, 2026-11-03) - Master Trainer waiting-view
usability MT-13/14/15 (user request 2026-11-02/03, online-
evaluated: search/filter/sort through the new pure
`table_filter.py` layer, keyboard load flow, rolling recent tables
in `master-settings.json` schema 3 + Size/Modified/Last-used
columns), plus the live-target takeover field fix (stale-lock
recovery attaches to the still-running game behind one
user-confirmed prompt when the owner is proven dead and only
target-side identities remain unproven); +61 tests; full main
suite 4,320 OK / 30 expected skips; catalog zero delta
`blocked-catalog-026-master-ui`; see the 0.26 section below.
Superseded 0.25 (build `native-20261103T062439Z-f4c16be9`, cut from
`main` @ `a861bfb`, 2026-11-03) - Master Trainer user control
MT-10/11/12 (user request 2026-11-02: explicit table load, process
picker + persisted attach mode, detach/user attach), plus the online
feature evaluation record in `master_trainer/ROADMAP.md`, the Tcl
test-harness hardening (`tests/native_tk_teardown.py`, test-only),
and the in-build reliability fix (state-home isolation in the
`run_master` cancel test + explicit Tk variable masters in
`master_ui.py`, first in-build run
`native-20261102T181843Z-ddfb63f0` exposed the dependence); +66
tests; full main suite 4,259 OK / 30 expected skips; catalog zero
delta `blocked-catalog-025-master-ui`; see the 0.25 section below.
Superseded 0.24 (build
`native-20261102T102029Z-fe358e35`, cut from `main` @ `a2777ed`,
2026-11-02; trainer tick sounds, user field request 2026-11-01;
branch `native-0.24-trainer-sounds`; see the 0.24 section below).
**Latest verified release:** 0.31, build
`native-20261105T080853Z-2e7f50a5` (cut from `main` @ `2def12f`,
2026-11-05): the 0.31 Master Trainer per-table live status +
color coding + status filter release (MT-23) - in-build
suite 4,414 OK / 30 expected skips,
`ce_inputs: []`, `runtime_unverified` deliberately kept per gate;
source ZIP `CT2Trainer-0.31-source.zip` sha256
`3bab9648208f6ed4cbafa919991cab19c7921597ac2075c5c8b964e17258c0f9`
(14,398,817 bytes), portable ZIP
`CT2Trainer-0.31-windows-portable.zip` sha256
`df5581ec5e8b0c0b99abdf35b914f08ec138b4470234b48c615304419a970839`
(49,679,202 bytes), frozen `CT2Trainer-Master.exe` (sha256
`811c0f85c143b632dd182646282ddb32c3293513a665eb62c8055f74f9c89dcb`)
next to the converter. Superseded 0.30, build
`native-20261104T131114Z-11522f68` (cut from `main` @ `2fbca94`,
2026-11-04): the 0.30 Master Trainer table details + live
load-gate preview release (MT-22) - in-build
suite 4,386 OK / 30 expected skips,
`ce_inputs: []`, `runtime_unverified` deliberately kept per gate;
source ZIP `CT2Trainer-0.30-source.zip` sha256
`091b379c132e277c19f519705dcccc4c0817e8e7e614e5baf2f14bbe3fe414a3`
(14,387,690 bytes), portable ZIP
`CT2Trainer-0.30-windows-portable.zip` sha256
`f4476bb08e3e65e6db9cd35bfe7a72408a555b8525bd6a10f8b794f943083d54`
(49,669,933 bytes), frozen `CT2Trainer-Master.exe` (sha256
`9d0a525a78dfbfffb906261ad42e435c5414cb6cb0189dd78c73910063f67643`)
next to the converter. Superseded 0.29, build
`native-20261104T094808Z-50af0517` (cut from `main` @ `de3e4ff`,
2026-11-04): the 0.29 Master Trainer UI/UX revamp release
(MT-19 trainer-focus mode + MT-20 discoverability) - in-build
suite 4,370 OK / 30 expected skips,
`ce_inputs: []`, `runtime_unverified` deliberately kept per gate;
source ZIP `CT2Trainer-0.29-source.zip` sha256
`2f5ce6e446f8d9885cd653580b5e194a2a0fc524eba7b5f684fe1f1a0e1da3d4`
(14,378,934 bytes), portable ZIP
`CT2Trainer-0.29-windows-portable.zip` sha256
`98c63c368bc2cccd68335e9db94a3b897abbbb815730c97912e3068805fad226`
(49,667,528 bytes), frozen `CT2Trainer-Master.exe` (sha256
`88e6ee99aa4c46973945e462ca956977e9942a1e8b30630aa2570107540f2de8`)
next to the converter. Superseded 0.28, build
`native-20261103T161621Z-ea8fde2f` (cut from `main` @ `d7f4cf0`,
2026-11-03): the 0.28 Master Trainer pinned/favorite tables release
(MT-18) - in-build suite 4,357 OK / 30 expected skips,
`ce_inputs: []`, `runtime_unverified` deliberately kept per gate;
source ZIP `CT2Trainer-0.28-source.zip` sha256
`13f4b2222a83f9e4588d388b4120beaf8018a091a05364029ae2a950c0dabb1a`
(14,363,765 bytes), portable ZIP
`CT2Trainer-0.28-windows-portable.zip` sha256
`d656835a69ece75ff6adaa5ce766385327fb9ec08d89837ad772425dafe91ce3`
(49,658,473 bytes), frozen `CT2Trainer-Master.exe` (sha256
`c12dcea5bb8a609dae4df36f44827ab5269c9e1015cb723067ed98dc100bf99b`)
next to the converter. Superseded 0.27, build
`native-20261103T145543Z-b29b3688` (cut from `main` @ `8aa0815`,
2026-11-03): the 0.27 Master Trainer waiting-view settings release
(MT-16/17) - in-build suite
4,342 OK / 30 expected skips, `ce_inputs: []`,
`runtime_unverified` deliberately kept per gate; source ZIP
`CT2Trainer-0.27-source.zip` sha256
`264b42d6c42dac1bb434c1d0591e82ac0bec69e61e1a1c75047c6aa58126f40e`
(14,357,294 bytes), portable ZIP
`CT2Trainer-0.27-windows-portable.zip` sha256
`bfcf2abc885122dfa8653fcfd0046323e7112f59c0850958688e36e014ebc135`
(49,654,613 bytes), frozen `CT2Trainer-Master.exe` (sha256
`9762c8bdc2298c16bd82779f206d9a885a449261a6428187c3bd2155fc5bf1bc`)
next to the converter. Superseded 0.26, build
`native-20261103T112811Z-59a6b3d5` (cut from `main` @ `c114ec2`,
2026-11-03): the 0.26 Master Trainer waiting-view usability release
(MT-13/14/15 + live-target takeover field fix) - in-build suite
4,320 OK / 30 expected skips, `ce_inputs: []`,
`runtime_unverified` deliberately kept per gate; source ZIP
`CT2Trainer-0.26-source.zip` sha256
`3d62f80cdfb95d8439d4a2f2150002976795faad313fa75d47aeb4fb92bb49bd`
(14,348,462 bytes), portable ZIP
`CT2Trainer-0.26-windows-portable.zip` sha256
`49be1d286999ed175737edb073c5ab83533c40cccc7e636685a256a0b07004b3`
(49,653,968 bytes), frozen `CT2Trainer-Master.exe` (sha256
`895f937ed5c228c09b97edba28aa9dc4ad228abd58585f73080f40ab265bc031`)
next to the converter. Superseded 0.25, build
`native-20261103T062439Z-f4c16be9` (cut from `main` @ `a861bfb`,
2026-11-03): the 0.25 Master Trainer user-control release
(MT-10/11/12 + Tcl test-harness hardening + in-build reliability fix)
- in-build suite 4,259 OK / 30 expected skips, `ce_inputs: []`,
`runtime_unverified` deliberately kept per gate; source ZIP
`CT2Trainer-0.25-source.zip` sha256
`64f8c3082cff50687b1962234c17a82e2a2f0c19eb1112ece06a0a25132f35be`
(14,324,774 bytes), portable ZIP
`CT2Trainer-0.25-windows-portable.zip` sha256
`774266f7e2c9dc69f4d8cfc963309b9907442ec6b5343ff629b9e30c04049653`
(49,633,196 bytes), frozen `CT2Trainer-Master.exe` (sha256
`8736f73e762b57a8f337bf8fa04c2c16f8622c4d99e7dd7f2167b2c9999e3d8f`)
next to the converter. Superseded 0.24, build
`native-20261102T102029Z-fe358e35` (built from `main` at `a2777ed`,
2026-11-02): the 0.24 trainer tick sounds release (see the 0.24
section below) - in-build suite 4,193 OK / 30 expected skips,
`ce_inputs: []`, `runtime_unverified` deliberately kept per gate;
source ZIP `CT2Trainer-0.24-source.zip` sha256
`dfdd8cfcca90a2789bf544d8f8de4e34941067feeb2b32ce8d550f98e5bc4eb6`
(14,298,696 bytes), portable ZIP
`CT2Trainer-0.24-windows-portable.zip` sha256
`12262cf16e906c3811ade0a8c582b7a1057c834a3110aff004dfd13b3067e7ab`
(49,618,009 bytes), frozen `CT2Trainer-Master.exe` (sha256
`5f3a66400c2c1775e6fc50ad6bbbc36aa8a6bcf8b58fe56507117dc33683494d`)
next to the converter. Superseded 0.23, build
`native-20261101T145310Z-a160bae4` (built from `main` at `6e3ec98`,
2026-11-01): the 0.23 Master Trainer roadmap release - MT-6/MT-7/
MT-8/MT-9 (frozen `CT2Trainer-Master.exe` now part of every build,
per-table settings sidecar, documented SteamOS/CheatDeck route,
load-time table compatibility & size gate with graceful named load
failures), waiting-view observability, ask-on-first-start
table-folder parameter, plus the same-day field fixes (placeholder
headings no longer create plan-level symbol dependencies; SC2
hotkey-bridge field fix from the 0.22.1 lane) - see the 0.23 section
below. In-build suite 4,176 OK / 30 expected skips, `ce_inputs: []`,
`runtime_unverified` deliberately kept per gate. Superseded 0.22,
build `native-20261101T075049Z-f32c112d` (built from `main` at
`2b24a1c`, 2026-11-01): the 0.22 FO4 field-fix cycle release -
bounded automatic re-arm of ScanMiss enable failures (30 s x 10
attempts, budget reset per (re-)attach, armed set survives target
exit) plus manual "Try again" / "Re-attach" actions (merge `a12a0b6`,
+17 tests; zero catalog delta `blocked-catalog-022-rearm`; the SC2
0.19 hotkey-bridge field findings are recorded in the section below -
the fix itself ships in 0.23 via the 0.22.1 lane). In-build suite
4,061 OK / 30 expected skips, `ce_inputs: []`,
`runtime_unverified` deliberately kept per gate.
Superseded 0.21, build
`native-20261031T211046Z-14707e12` (built from `main` at `9a725a8`,
2026-10-31): the 0.21 feature release - RT-5 complete (item B
CheatCodes code-patch plan path, merge `9ef4a74`, +26 tests, catalog
remeasure `blocked-catalog-020-rt5-be`: 117,634 -> 117,809 total,
116,581 -> 116,756 supported, 1,053 blocked, 60,161 staged, 0 load
errors, zero newly blocked; item E `messageDialog` safe logged no-op,
merge `b8bb4ee`, +22 tests, zero catalog delta
(`blocked-catalog-rt5e-iteme`)) plus the new Master Trainer (one
long-lived trainer window: incremental folder table index,
cross-platform process watch, unique-match auto-load / multi-table
picker, handoff into the exact standalone trainer UI, per-table on/off
persistence; MT-1..MT-5, 141 tests - see the Master Trainer section
below). In-build suite 4,044 OK / 30 expected skips, `ce_inputs: []`,
`runtime_unverified` deliberately kept per gate. Superseded 0.20.1,
build
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

**0.21 Master Trainer (2026-10-31, released in build
`native-20261031T211046Z-14707e12` cut from `main` at `9a725a8`;
branch `native-0.20-master-trainer` merged into `main`):** one
long-lived trainer
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
development. In-build suite on the 0.21 build: 4,044 OK / 30 expected
skips, 0 failures (fully green at the canonical build path, incl.
the 3 path-dependent baseline-reproducibility tests); catalog
unchanged (zero Master Trainer effect; latest remeasure
`blocked-catalog-020-rt5-be`).

**0.22 field cycle (2026-11-01): FO4 re-arm + SC2 hotkey-bridge
findings (released in build `native-20261101T075049Z-f32c112d`).**
Field tests 2026-10-30/31: Fallout 4 (0.20, Steam Deck /
Proton) and The Sinking City 2 (0.19; Windows x2 + Deck x1); debug
logs kept local-only (clean-room rule).

- **FO4 (0.20, Deck, 2026-10-31 13:37-13:45 UTC, target pid 696):** 8
  auto-on wishes queued pre-attach, auto-attach OK, but 6 of 8 wish
  restores failed `ScanMiss` while the game was still loading (43 OK;
  1052 AOB first match OK then second ScanMiss); 15+ manual taps all
  ScanMiss; value-read failures on 8 identifiers while the engine
  loaded (expected - unresolved pointer chains; 0.19
  `value-read-failed` observability covers them). Shipped fix: bounded
  automatic re-arm (30 s x 10 attempts, armed by any ScanMiss enable
  failure, budget reset per (re-)attach, armed set survives target
  exit) + manual "Try again" row action + top-level "Re-attach"
  button; `tests/test_native_rearm.py` (+17). Catalog zero delta
  (`blocked-catalog-022-rearm`).
- **SC2 (0.19, 3 sessions) hotkey-bridge defects - NOT fixed in 0.22**
  (hotkey-bridge code unchanged; next field-fix cycle):
  (1) the missing-`RegisterHotKeyW` guard flag set in
  `hotkey_bridge.py:343-351` is never checked by `register_hotkey`
  (:404) / `unregister_hotkey` (:408) -> raw `AttributeError` instead
  of the named non-blocking `HotkeyRegistrationError`; (2) the error
  escapes toggle/poll and hard-blocks the whole engine - S1 entry 198
  shows `toggle-ok` **and** `toggle-failed` (the programmatic enable
  had succeeded), and S2's `poll-crashed` -> `engine-blocked` then
  refuses every toggle incl. `close()`; (3) deterministic close
  failure on every platform (S1/S2 Windows + S3 Deck): the bridge
  window is created on the main thread (`connect()`, :381) while the
  loop thread (:393, `GetMessageW(NULL)`) pumps its own empty queue,
  so `WM_BRIDGE_QUIT` is only deliverable on the main thread, but
  `destroy()` (:415) blocks that thread in `join(timeout=5.0)` ->
  guaranteed 5 s timeout ("hotkey bridge message loop did not stop
  within 5s") -> `DestroyWindow` never reached -> daemon loop thread
  AVs in `GetMessageW` during process teardown (3x) -> state lock
  survives the crash.
- **Other findings:** transient-read `PatchConflict` (Win32 299,
  `ReadProcessMemory failed`) ~1 h after attach (S1 22:19:19) - a
  transient read error must not become a receipt change; state-lock
  first-restart refusal ("not proven dead in both observations
  (absent)") although both dead PIDs were absent, second start
  recovered via `StaleStateRecoverable` (S2 12:31); wish persisted
  before `toggle-failed` (S1 entry 198) - violates the "only confirmed
  ON-switches are persisted" rule.
- **Open field verification:** no `WM_HOTKEY` dispatch observed in
  either log yet - next field test should press a bound hotkey and
  expect the `hotkey-*` events.

**0.24 content on main (2026-11-01, branch
`native-0.24-trainer-sounds`): trainer tick sounds (user field
request 2026-11-01).** The generated trainer now plays the tick
sounds of the original native trainer generator's character: a
distinct double tick on a confirmed (re-)attach to the game process,
and a high/low single tick on every confirmed on/off toggle of an
item (manual row switch, group heading toggle, and hotkey-dispatched
activation toggles - CE parity: the original generated trainer
sounds on every toggle, not only UI taps).  Behavior reference
(read-only, never copied): CE 7.5's native trainer generator ships
two built-in tick sounds (`Sounds.RC` registers `tick1.wav` /
`tick2.wav` as the `BUILDIN_ACTIVATE` / `BUILDIN_DEACTIVATE` RCDATA
resources; measured ~28 ms, 8-bit unsigned mono, 11025 Hz, ~4.4 kHz
activate / ~3.8 kHz deactivate, played through Win32 winmm
`PlaySound` with `SND_MEMORY | SND_ASYNC`).  The reference corpus
carries no table-embedded audio files, so that built-in pair is the
original sound set.  Clean-room: the ticks are synthesized
deterministically in code in the same format and pitch character; no
CE asset bytes are copied.

- **`trainer_sounds.py` (new):** deterministic synthesis of the three
  ticks as 8-bit unsigned mono 11025 Hz RIFF/WAVE bytes (on: 5512.5
  Hz / 28 ms; off: 3675 Hz / 28 ms; attach: double 3675 Hz tick with a
  silent gap); module-cached buffers (`SND_MEMORY` requires the
  buffer to stay alive for the playback); `play_sound(kind)` is
  best-effort - Win32 winmm `PlaySound` with `SND_MEMORY |
  SND_ASYNC`, a stable named result string
  (`played` / `skipped: non-windows platform` / `refused:
  <reason>`), and never raises into the UI.
- **`ui.py`:** the old 880/440 Hz sine `play_toggle_sound` helper is
  replaced by `trainer_sounds.play_sound` at every confirmed toggle
  site (row switch and group heading toggle now both sound) and on
  the attach-success transition detected in `TrainerWindow.poll()`
  (the engine memory handle going from nothing to a live target
  plays the attach tick exactly once per (re-)attach; failed attach
  attempts stay silent).
- **`engine.py`:** confirmed activation toggles dispatched through
  the hotkey path (OS bridge drain or programmatic
  `dispatch_hotkey`) surface as `(record_id, resulting-active)`
  pairs through `TrainerEngine.pop_hotkey_ui_toggles()` so the UI
  tick matches CE's on-every-toggle behavior; value-action hotkeys
  are not recorded.
- Tests: new `tests/test_native_trainer_sounds.py` +21 (synthesis
  shape/determinism/character, named playback refusals, hotkey-surface
  recording contract, real-Tk attach-transition / manual-toggle /
  group-toggle / hotkey-toggle wiring); `tests/test_native_ui_tone.py`
  (4 tests) superseded and removed with the old helper.  Full main
  suite 4,193 OK / 30 expected skips on `main` @ `60dbc21` (2026-11-02); catalog remeasure `blocked-catalog-024-sounds`: zero delta
  vs `blocked-catalog-023-field-fixes` (151/151 loaded, 117,809 total
  / 116,756 supported / 60,161 staged / 1,053 blocked / 0 load
  errors; per-table changes 0).
  Build `native-20261102T102029Z-fe358e35` (2026-11-02, cut from
  `main` @ `a2777ed`): in-build suite 4,193 OK / 30 expected skips,
  `ce_inputs: []`, `runtime_unverified` deliberately kept per gate;
  source ZIP `CT2Trainer-0.24-source.zip` sha256
  `dfdd8cfcca90a2789bf544d8f8de4e34941067feeb2b32ce8d550f98e5bc4eb6`
  (14,298,696 bytes), portable ZIP
  `CT2Trainer-0.24-windows-portable.zip` sha256
  `12262cf16e906c3811ade0a8c582b7a1057c834a3110aff004dfd13b3067e7ab`
  (49,618,009 bytes), frozen `CT2Trainer-Master.exe` sha256
  `5f3a66400c2c1775e6fc50ad6bbbc36aa8a6bcf8b58fe56507117dc33683494d`
  (16,896,995 bytes) in the run folder, the payload inventory and
  the portable ZIP. Field test of the tick sounds on a live game
  is pending.

**0.32 content on main (2026-11-06, root-direct; the 0.32 build is
cut from this content - 0.31 remains the latest verified release):
Master Trainer per-table entry count + blocked count (background plan
analysis, MT-24).**
The 0.32 feature was evaluated against online trainer front-end and
trainer-manager UX patterns (FLiNG per-trainer "N Options" /
option-count metadata - per-table entry counts surfaced in the list
tell the user what a table actually offers and what cannot run in it
before loading; game-trainer-manager (Karasukaigan)
organize/search workflows; Cheat Happens Trainer Manager v2
inspect-before-load lineage - see the Master Trainer ROADMAP "0.32
per-table entry count + blocked count (background plan analysis)"
section). Adopted: MT-24, the candidate deliberately deferred in
0.26/0.27/0.29/0.30/0.31 ("the entry-count / blocked-count columns
need background plan-analysis infrastructure"). Remaining candidate
(unchanged): the MT-21 multi-column trainer grid.
- **MT-24 per-table entry count + blocked count:** the waiting-view
  tree gains two columns between Detail and Size - **Entries**
  (actionable record count: the supported script / value records,
  i.e. the real cheat options) and **Blocked** (the blocked record
  count of the same analysis). The analysis runs in the background:
  one daemon thread (`master_trainer/analysis_worker.py`, queue limit
  64, dedupe by table content sha, only tables with a bound process
  name are queued) through the tested `compile_table` plan path - no
  Lua execution, no target attach, the same static proof the corpus
  audit uses. The columns show "..." while pending and "-" on a named
  compile failure, the counts once analyzed; a blocked count > 0
  appends the bounded "N blocked" note to the detail column after the
  pin marker. Results persist in `table-analysis.json` (schema 1,
  under the state home, keyed by table content sha256, LRU-bounded to
  1024 entries, top-8 blocked reasons per table, 200-char error
  detail) - a content change re-analyzes, an unchanged table reuses
  the cached entry; the pure decision layer is
  `master_trainer/table_analysis.py` (`counts_from_plan` /
  `blocked_reasons_from_plan` / `ok_analysis` / `failed_analysis` /
  `AnalysisStore` with strict key-set + checksum + timestamp + count
  validation, `AnalysisRefusal`). The worker is not auto-started: the
  waiting view owns the lifecycle (start / resume + queue at the end
  of the view build, pause on trainer entry after the attach gate,
  stop + clear on close); the meta line shows the live
  "analyzing N table(s)" figure while the queue has work; the MT-22
  table-details window gains the analysis block (`table_details.py`
  `analysis` kwarg): pending / "N entries (M blocked) of T records" +
  top blocked reasons / "failed: <reason>". Display-side observation
  only - it never blocks, alters, or delays the MT-9 load gate, which
  re-checks the table independently at load time. Zero catalog effect
  (no table-parsing change).
- +69 tests (57 in `tests/test_native_master_analysis.py` new: the
  pure counts / reasons builders, the ok / failed analysis builders,
  the store's strict validation (unknown fields, wrong sha, bad
  counts, checksum mismatch), LRU eviction by `analyzed_at` with sha
  tie-break, the refusal codes, and the `active_workers()` live-worker
  registry lifecycle; 12 in
  `tests/test_native_master_ui_mt24.py` new: the column wiring +
  pending / failed / pinned / group-row shaping, the queue discipline
  (unbound tables never queued, rescan re-queues on content change
  only), the details-window analysis rows, the trainer-entry pause,
  the close stop + reference clear, the window-created default worker
  with the real compile path); plus the cross-module test-isolation
  fix - the shared Tk test teardown now stops every live analysis
  worker (registry in `analysis_worker.py`) before releasing the
  root, so window tests no longer leak worker threads into later
  engine/timing modules; full main suite 4,483 OK / 30 expected
  skips (4,414 from the 0.31 content + 69 new); catalog remeasure
  `blocked-catalog-032-analysis` (3-chunk deep-equal audit over the
  151 reference tables, 2026-11-06): 151/151 loaded, 0 load errors,
  117,809 total / 116,756 supported / 60,161 staged / 103,607
  actionable / 12,974 headings / 1,053 blocked - **zero delta** vs
  `blocked-catalog-031-status` (per-table count/reason/sha changes:
  0); feature matrix unchanged (42/42, 7,475/7,475 over
  `w4b4-case30-20261020081722Z`); AP-11 0/6,143. VERSION bumped to
  0.32 with the changelog entry in the same change.

**0.31 released (build `native-20261105T080853Z-2e7f50a5`, cut from
`main` @ `2def12f`, 2026-11-05): Master Trainer per-table live
status + color coding + status filter (MT-23).**
The 0.31 feature was evaluated against online trainer front-end and
trainer-manager UX patterns (FLiNG per-trainer "Game Version" /
"Last Updated" / option-count metadata - per-table freshness and
state facts surfaced in the list are a recognized pattern; Game
Cheats Manager (dyang886) "smart launcher" - drop tables +
trainers, detect the installed games, associate trainer to game,
auto-update: the detection + trainer-to-game association are already
covered by MT-2/MT-17, auto-update is out of scope per the
offline/hash-verified build policy, and the Python + Tkinter
implementation corroborates the Master's stack; game-trainer-manager
(Karasukaigan) download/import/organize/search around a trainer
list; CheatDeck (SheffeyG) Steam Deck launch options - the
documented MT-7 route). Adopted: MT-23, the candidate deliberately
deferred in 0.26/0.27/0.29/0.30 ("per-table status / color-coding").
Remaining candidates (unchanged): the MT-21 multi-column trainer
grid and the entry-count / blocked-count columns (they need
background plan-analysis infrastructure).
- **MT-23 per-table live status + color coding + status filter:**
  the waiting-view Status column shows the table's state RIGHT NOW,
  not only the cached state of the last scan - one bounded `stat`
  per visible row per render against the index entry: `ok` /
  `running` (a bound process is up, the table loadable) / `changed`
  (the file drifted since the last scan) / `missing` (the file is
  gone) / `unreadable` (the last scan could not read/parse it, the
  named detail surfaces); cheapest fact first, live facts outrank
  the cached scan state - the same order the MT-9 gate proves at
  load time. Rows are color coded (the default colors for ok /
  running, amber `#e5c07b` for changed, red `#ff7b72` for missing /
  unreadable - the two tree tags configured in the waiting view),
  and the persisted "Status: all / ok / attention" header cycle
  (between the view button and the filter entry) filters the list
  to the loadable rows or to the rows the gate would refuse right
  now. `master-settings.json` schema 5 -> 6: `view_status` (one of
  `VIEW_STATUS_FILTERS`, mirrored by
  `table_status.VIEW_STATUS_FILTERS`); schema-5 documents promote
  with `view_status=""`, a schema-5 document carrying the field is
  refused as an unknown field (the MT-11/15/16/18 discipline).
  `MasterApp.set_view_settings` gains the 4th parameter
  `status_filter` (validated + re-persisted; every existing change
  point passes the current mode through, so sort/view/filter
  changes never reset the status filter); `_visible_tables()`
  applies the status filter between the query filter and the pin
  float; the meta line gains the active `status filter: X` part and
  the live `attention: N` count (how many indexed tables the MT-9
  gate would refuse right now - shown only when N > 0). The pure
  decision layer is `master_trainer/table_status.py`
  (`row_file_status` / `row_status` / `row_tag` /
  `filter_rows_by_status`, `ATTENTION_STATUSES`,
  `VIEW_STATUS_FILTERS` - no OS access, no index mutation); the
  in-app `ui_flow_text()` and the reviewable `master_trainer/UI.md`
  document the new header control, the live Status column and the
  persistence row.
- +28 tests (4 schema-6 state in `tests/test_native_master_state.py`
  + 24 in `tests/test_native_master_ui_mt23.py` new: the pure layer
  - the live file state per fingerprint, the running-loses-to-
  attention contract, the tag per code, the filter reshaping per
  mode + the named refusal, the constant mirror against the state
  schema; the Tk wiring - the cycle / persist / restore, the other
  UI changes keeping the mode, the live changed / missing flags +
  tags, the ok / attention row shaping, the meta line); full main
  suite 4,414 OK / 30 expected skips (4,386 from the 0.30 content +
  28 new); catalog remeasure `blocked-catalog-031-status` (3-chunk
  deep-equal audit over the 151 reference tables, 2026-11-05):
  151/151 loaded, 0 load errors, 117,809 total / 116,756 supported
  / 60,161 staged / 103,607 actionable / 12,974 headings / 1,053
  blocked - **zero delta** vs `blocked-catalog-030-details`
  (per-table count/reason/sha changes: 0); feature matrix unchanged
  (42/42, 7,475/7,475 over `w4b4-case30-20261020081722Z`); AP-11
  0/6,143. VERSION bumped to 0.31 with the changelog entry in the
  same change. The 0.31 build
  `native-20261105T080853Z-2e7f50a5` was cut from `main` @
  `2def12f` (2026-11-05): in-build suite 4,414 OK / 30 expected
  skips, `ce_inputs: []`, `runtime_unverified` deliberately kept
  per gate; source ZIP `CT2Trainer-0.31-source.zip` sha256
  `3bab9648208f6ed4cbafa919991cab19c7921597ac2075c5c8b964e17258c0f9`
  (14,398,817 bytes), portable ZIP
  `CT2Trainer-0.31-windows-portable.zip` sha256
  `df5581ec5e8b0c0b99abdf35b914f08ec138b4470234b48c615304419a970839`
  (49,679,202 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `811c0f85c143b632dd182646282ddb32c3293513a665eb62c8055f74f9c89dcb`,
  16,948,380 bytes, ships next to the converter).

**0.30 released (build `native-20261104T131114Z-11522f68`, cut from
`main` @ `2fbca94`, 2026-11-04): Master Trainer table details + live
load-gate preview (MT-22).**
The 0.30 feature was evaluated against online trainer front-end and
trainer-manager UX patterns (FLiNG per-trainer version / "Last
Updated" metadata, game-trainer-manager organize/search workflows,
Game Cheats Manager .ct handling FAQ, Cheat Happens Trainer Manager
v2 portable + last-used pinning - see the Master Trainer ROADMAP
"0.30 table details + load-gate preview" section). Adopted: MT-22.
Deliberately deferred (documented): the MT-21 multi-column trainer
grid, the entry-count / blocked-count columns and the per-table
status / color-coding.
- **MT-22 table details + live load-gate preview:** right-clicking
  a waiting-view row offers "Table details" first - a read-only
  Toplevel (title "Table details - <rel>", transient, non-resizable,
  Close button) with the indexed facts for the table: path,
  folder, size, modified, bound processes, index status (ok /
  unreadable: <reason>), pin state, last used (the persisted UTC
  timestamp or "never"), running PIDs (deduped, sorted, "not
  running" when none), content sha256 (last scan - first 12 hex +
  "...") - plus the on-demand `gate_table_for_load` re-check: the
  same pass MT-9 runs at load time, so a refusal shows the stable
  named code + displayable detail (a stale / changed / unreadable
  table is explained at inspection time, not only at load time); a
  passing gate proves the file matches the last scan. One window (a
  second open lifts + focuses instead of duplicating); closed on
  trainer entry with the rest of the waiting view; no index entry
  leaves a named status line instead of a window. The row builder
  is pure in `master_trainer/table_details.py` (`format_size` /
  `format_mtime` / `gate_line` - "not checked" / "OK (loadable -
  the file matches the last scan)" / "<code>: <detail>" with named
  fallbacks; `table_detail_lines` - the 11 ordered (label, value)
  rows); the only I/O is the bounded gate re-check under the load
  limit. The in-app `ui_flow_text()` and the reviewable
  `master_trainer/UI.md` document the new row-menu entry
  (keyboard map + table-tree section).
- +16 tests (`tests/test_native_master_ui_mt22.py`); full main
  suite 4,386 OK / 30 expected skips (4,370 from the 0.29 content +
  16 new); catalog remeasure `blocked-catalog-030-details`
  (chunked 64x3 audit over the 151 reference tables, 2026-11-04):
  151/151 loaded, 0 load errors, 117,809 total / 116,756 supported
  / 60,161 staged / 103,607 actionable / 12,974 headings / 1,053
  blocked - **zero delta** vs `blocked-catalog-029-trainer-focus`
  (per-table count/reason/sha changes: 0); feature matrix unchanged
  (42/42, 7,475/7,475 over `w4b4-case30-20261020081722Z`); AP-11
  0/6,143. VERSION bumped to 0.30 with the changelog entry in the
  same change. The 0.30 build
  `native-20261104T131114Z-11522f68` was cut from `main` @
  `2fbca94` (2026-11-04): in-build suite 4,386 OK / 30 expected
  skips, `ce_inputs: []`, `runtime_unverified` deliberately kept
  per gate; source ZIP `CT2Trainer-0.30-source.zip` sha256
  `091b379c132e277c19f519705dcccc4c0817e8e7e614e5baf2f14bbe3fe414a3`
  (14,387,690 bytes), portable ZIP
  `CT2Trainer-0.30-windows-portable.zip` sha256
  `f4476bb08e3e65e6db9cd35bfe7a72408a555b8525bd6a10f8b794f943083d54`
  (49,669,933 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `9d0a525a78dfbfffb906261ad42e435c5414cb6cb0189dd78c73910063f67643`,
  16,940,058 bytes, ships next to the converter).

**0.29 released (build `native-20261104T094808Z-50af0517`, cut from
`main` @ `de3e4ff`, 2026-11-04): Master Trainer UI/UX revamp (MT-19
trainer-focus mode + MT-20 discoverability).** The user field request of 2026-11-04 (the
waiting table list must shrink/collapse so the trainer items get
maximum space once a process is identified and the trainer
attaches; generally more accessible UI; the UI flow documented so
it can be reviewed/improved) was evaluated against the local
shared-root trainer handoff plus the standing trainer-manager UI
evaluations (Trinity profiles, Cheat Happens AURORA accessibility,
keyboard-shortcut databases, WCAG/platform accessibility guidance -
see the Master Trainer ROADMAP "0.29 trainer-focus + discoverability"
section). Adopted: MT-19, MT-20. Deliberately deferred (documented
candidate MT-21, separate cycle): the multi-column trainer grid -
the single-column canvas grid is the validated touch-first design
(`ui_rows.py` pure row model + `ui_layout.py` + the 1-D hit-testing,
exhaustively tested and shared with the standalone trainer); a
column layout rewrites the pure row model, the pagination and the
2-D hit-testing and changes the standalone trainer as well.
- **MT-19 trainer-focus mode:** the whole waiting view now lives in
  one container frame (`MasterWindow._waiting_frame`,
  `fill=both expand=True` on the shared root) - the header, the
  folder/meta/running lines, the table-tree frame and the status
  bar are all its children. `_enter_trainer()` destroys the
  container immediately after the engine is up (before the
  `TrainerWindow` is built) and drops every waiting-view widget
  reference, so the trainer row grid owns the full window instead
  of sharing it with the table list, and the poll loop / handlers
  never touch a destroyed widget (the poll tick already
  early-returns in trainer mode). The trainer-constructor failure
  path rebuilds the waiting view before `_fail_trainer_start()` so
  the waiting loop and its loop guard stay consistent;
  `_back_to_master()` is unchanged (destroy-all + rebuild). The
  open UI-flow Toplevel is closed with the teardown. +6 UI tests in
  `tests/test_native_master_ui_mt19.py`.
- **MT-20 discoverability:** the module function `ui_flow_text()`
  (headless-testable) is the plain-language UI-flow document - the
  same content as the reviewable `master_trainer/UI.md` in the
  package (ships in the source ZIP through the existing `.md`
  allowlist); the new "UI flow" header button opens it in a
  read-only Toplevel (single window: a second click lifts +
  focuses the open window instead of duplicating; closed on
  trainer entry). F5 re-scans the folder from anywhere in the
  waiting view (root binding, guarded no-op in trainer mode like
  the existing "/" binding). The table tree takes the initial
  focus on build (`focus_set` at the end of
  `_build_waiting_view`), so arrow keys and Enter work immediately
  without a first click. The "Retry load" re-arm moves out of the
  root-level button below the status strip into the status bar
  next to the attach toggle and the Recent button. +7 UI tests in
  `tests/test_native_master_ui_mt19.py`.
- Full main suite 4,370 OK / 30 expected skips; catalog zero
  delta `blocked-catalog-029-trainer-focus` (151/151 loaded, 0
  load errors, 117,809 total / 116,756 supported / 1,053 blocked,
  zero delta vs `blocked-catalog-028-pin`); feature matrix
  unchanged (42/42, 7,475/7,475 over
  `w4b4-case30-20261020081722Z`); AP-11 0/6,143. VERSION bumped to
  0.29 with the changelog entry in the same change. The 0.29 build
  `native-20261104T094808Z-50af0517` was cut from `main` @ `de3e4ff`
  (2026-11-04): in-build suite 4,370 OK / 30 expected skips,
  `ce_inputs: []`, `runtime_unverified` deliberately kept
  per gate; source ZIP `CT2Trainer-0.29-source.zip` sha256
  `2f5ce6e446f8d9885cd653580b5e194a2a0fc524eba7b5f684fe1f1a0e1da3d4`
  (14,378,934 bytes), portable ZIP
  `CT2Trainer-0.29-windows-portable.zip` sha256
  `98c63c368bc2cccd68335e9db94a3b897abbbb815730c97912e3068805fad226`
  (49,667,528 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `88e6ee99aa4c46973945e462ca956977e9942a1e8b30630aa2570107540f2de8`,
  16,937,063 bytes, ships next to the converter).

**0.28 released (build `native-20261103T161621Z-ea8fde2f`, cut from
`main` @ `d7f4cf0`, 2026-11-03): Master Trainer
pinned/favorite tables (MT-18).** The 0.28 feature
set was evaluated against online table/list UX patterns (VGC Shelf
"sort, pin, archive"; see the Master Trainer ROADMAP "0.27
waiting-view settings + process groups" follow-up research and the
adopted candidate). Adopted: MT-18. Deliberately deferred
(documented): entry-count / blocked-count columns, per-table
status / color-coding.
- **MT-18 pinned / favorite tables:**
  `master-settings.json` schema 4 → 5: `pinned_tables` (relative
  table paths, most recent pin first, capped at
  `PINNED_TABLES_LIMIT` = 25, each a non-empty string within the
  table-path length bound). Schema-4 documents promote on load
  with `pinned_tables=[]`; a schema-4 document carrying the field
  is refused as an unknown field (foreign schema, never silently
  promoted - the same discipline as MT-11/15/16). The pure
  `table_filter.pin_tables` reshaping of the already-sorted-and-
  filtered row set (never adds or drops tables): pinned rows first
  in pin order (casefolded comparison), the remainder keeps the
  input order, pin paths not in the row set (filtered out or
  gone) ignored. The row context menu offers "Pin to top" /
  "Unpin" (`MasterApp.set_table_pinned` validates - named
  `ValueError`s for cap / already pinned / not pinned - and
  re-persists immediately); a pinned table floats to the top of
  the list view and to the top of its process group in the
  grouped view (the pin set is applied after filter + sort,
  before the MT-17 grouping); the pin marker lives in the detail
  column ("pinned" / "pinned - PID …"), the first column stays
  the bare relative path (the row identity the load paths key
  off); a named refusal lands in the status line without a state
  change or a crash. +15 tests (4 schema-5 state + 4 pure pin +
  7 MT-18 UI).
- Full main suite 4,357 OK / 30 expected skips; catalog zero
  delta `blocked-catalog-028-pin` (151/151 loaded, 0 load errors,
  117,809 total / 116,756 supported / 1,053 blocked, zero delta
  vs `blocked-catalog-027-view`); feature matrix unchanged
  (42/42, 7,475/7,475 over `w4b4-case30-20261020081722Z`);
  AP-11 0/6,143. VERSION bumped to 0.28 with the changelog entry
  in the same change. The 0.28 build
  `native-20261103T161621Z-ea8fde2f` was cut from `main` @ `d7f4cf0`
  (2026-11-03): in-build suite 4,357 OK / 30 expected skips,
  `ce_inputs: []`, `runtime_unverified` deliberately kept
  per gate; source ZIP `CT2Trainer-0.28-source.zip` sha256
  `13f4b2222a83f9e4588d388b4120beaf8018a091a05364029ae2a950c0dabb1a`
  (14,363,765 bytes), portable ZIP
  `CT2Trainer-0.28-windows-portable.zip` sha256
  `d656835a69ece75ff6adaa5ce766385327fb9ec08d89837ad772425dafe91ce3`
  (49,658,473 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `c12dcea5bb8a609dae4df36f44827ab5269c9e1015cb723067ed98dc100bf99b`,
  16,929,732 bytes, ships next to the converter).

**0.27 released (build `native-20261103T145543Z-b29b3688`, cut from
`main` @ `8aa0815`, 2026-11-03): Master Trainer waiting-view
settings persistence (MT-16) +
process-grouped waiting view (MT-17).** The 0.27 feature set was
evaluated against online table/list UX patterns (playR, Universal
Game Launcher, GamesList Manager, Game Cheats Manager) and
recorded in `master_trainer/ROADMAP.md` ("0.27 waiting-view
settings + process groups"). Adopted: MT-16/17 (both
deliberately deferred in 0.26). Deliberately deferred
(documented): entry-count / blocked-count columns, per-table
status / color-coding.
- **MT-16 persisted waiting-view settings:**
  `master-settings.json` schema 3 → 4: `view_filter` (the raw
  filter entry text, at most `VIEW_FILTER_MAX` = 200 characters,
  "" = no filter), `view_sort` (one of the table_filter sort
  modes) and `view_mode` ("list" flat rows / "process" grouped by
  bound process name). Schema-1/2/3 documents promote on load
  with the documented defaults ("" / "name" / "list"); a
  schema-3 document carrying a view_* field is refused as an
  unknown field (foreign schema, never silently promoted - the
  same discipline as MT-11/MT-15). The format-level constants
  live in `master_state` (the attach-mode pattern), pinned
  against the pure layer by a test.
  `MasterApp.set_view_settings(filter_query, sort_mode,
  view_mode)` validates (named `ValueError`s) and re-persists
  immediately; the window restores all three from the persisted
  document at construction; every UI change point re-persists
  (filter `<KeyRelease>`, sort cycle, view cycle, Esc clear).
  +4 state tests (`tests/test_native_master_state.py`) + 5 UI
  tests (`tests/test_native_master_ui_mt16.py`).
- **MT-17 process-grouped waiting view:** the pure
  `table_filter.group_tables_by_process` reshaping of the
  already-sorted-and-filtered row set (never adds or drops
  tables): one parent row per casefolded bound process name (a
  table bound to several names appears once under each of
  them), the tables without a bound name under "(no process
  binding)" last, within-group order = the caller's sort order.
  The "View: list/process" cycle button sits between the sort
  button and the filter entry (persisted through MT-16); the
  tree (`show="headings"`) renders the group label + "N
  table(s)" count in values[0] of the parent row (the text item
  is invisible with headings). Group rows are display-only -
  double-click, Enter and the row context menu are gated by
  `_is_table_row`, so a group row never loads; the children load
  through the ordinary MT-10 path. +8 pure tests
  (`tests/test_native_master_table_filter.py`) + 5 UI tests
  (`tests/test_native_master_ui_mt16.py`).
- Full main suite 4,342 OK / 30 expected skips; catalog zero
  delta `blocked-catalog-027-view` (151/151 loaded, 0 load
  errors, 117,809 total / 116,756 supported / 1,053 blocked,
  zero delta vs `blocked-catalog-026-master-ui`); feature matrix
  unchanged (42/42, 7,475/7,475 over
  `w4b4-case30-20261020081722Z`); AP-11 0/6,143. VERSION bumped
  to 0.27 with the changelog entry in the same change. The 0.27 build
  `native-20261103T145543Z-b29b3688` was cut from `main` @ `8aa0815`
  (2026-11-03): in-build suite 4,342 OK / 30 expected skips,
  `ce_inputs: []`, `runtime_unverified` deliberately kept per gate;
  source ZIP `CT2Trainer-0.27-source.zip` sha256
  `264b42d6c42dac1bb434c1d0591e82ac0bec69e61e1a1c75047c6aa58126f40e`
  (14,357,294 bytes), portable ZIP
  `CT2Trainer-0.27-windows-portable.zip` sha256
  `bfcf2abc885122dfa8653fcfd0046323e7112f59c0850958688e36e014ebc135`
  (49,654,613 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `9762c8bdc2298c16bd82779f206d9a885a449261a6428187c3bd2155fc5bf1bc`,
  16,929,639 bytes, ships next to the converter).

**0.26 released (build `native-20261103T112811Z-59a6b3d5`, cut from
`main` @ `c114ec2`, 2026-11-03): Master Trainer waiting-view
usability MT-13/14/15 (user request 2026-11-02/03) + live-target
takeover field fix.** With ~151
indexed tables (143 distinct hashes) the waiting view needed real
navigation; the feature set was evaluated against online table/list
UX patterns and recorded in `master_trainer/ROADMAP.md` ("0.26
waiting-view usability"). Adopted: MT-13/14/15. Deliberately
deferred (documented): group-by-process tree, persisted filter/sort,
entry-count / blocked-count columns.
- **MT-13 search / filter / sort:** new pure decision layer
  `table_filter.py` (no OS / index / state access): `filter_tables`
  (empty/whitespace query = the identity, input order preserved;
  otherwise a casefolded substring over the table's relative path
  AND any bound process name — a table matches when ANY bound name
  matches) and `sort_tables` (modes name / process / status; the
  casefolded relative path is the universal tie-breaker; in
  process mode unbound tables sort last; unknown mode raises
  `ValueError`). The waiting view renders
  `filter_tables(sort_tables(index.tables(), mode), query)`; row
  identity stays the relative path; the load picker and the
  auto-load path keep the full index. Filter and sort are
  session-only: they survive the trainer round-trip but are never
  persisted. Header filter entry (live re-render; meta line shows
  `filtered: N/M`) + "Sort: name/process/status" cycle button.
  +21 tests (`test_native_master_table_filter.py` + filter/sort UI
  tests in `test_native_master_ui_mt13.py`).
- **MT-14 keyboard flow:** double-click, Return and KP_Enter load
  the selected row through the ordinary MT-10 explicit-load path
  (named refusals included, no new load logic); arrow keys are
  built into the Treeview; "/" focuses the filter from anywhere in
  the waiting view (a no-op in trainer mode); Esc on the filter
  clears it and returns focus to the table list. +3 tests.
- **MT-15 recent tables + metadata columns:**
  `master-settings.json` schema 2 → 3: `recent_tables`, most recent
  first, capped at ten, each item `{"path", "at"}` with the
  persisted UTC timestamp `YYYY-MM-DDTHH:MM:SSZ` (strict format);
  schema-1/2 documents promote on load with `recent_tables=()`,
  and a schema-2 document carrying the field is refused as an
  unknown field. `MasterApp.remember_recent_table` (prepend /
  dedup / cap / persist) is called at all three successful load
  points. The meta line shows `recent: a, b, c (N more)`, the
  status frame gains the "Recent: <path>" one-click load button,
  and the tree gains indexed Size (compact B/KB/MB), Modified
  (local `YYYY-MM-DD HH:MM`) and Last-used columns; the window
  grows to 1160x600 (minsize 900x420). +18 tests.
- **Live-target takeover field fix:** when a stale `state.lock`
  blocks the startup and the owner session is proven dead in both
  observations while only target-side identities remain unproven
  (no other refusal reasons), the recovery archives the state
  byte-for-byte and, behind one user-confirmed prompt, attaches to
  the still-running game; saved wishes are re-applied (code-patch
  adopt idempotent; AOB ScanMiss entries surface named scan errors
  + bounded re-arm). Unprovable or live owner, foreign artifact or
  any extra reason keeps the strict refusal. +19 tests
  (`test_native_live_target_takeover.py`).
- Regression fixes: `_meta_text()` re-gained its `state: <home>`
  line; `test_empty_state_roundtrip` expects the schema-3
  `recent_tables: []` payload; the stored-folder test persists
  through the current-schema state (old schemas are refused by
  `master_state_to_bytes` by design); the rescan test asserts the
  7-value row. Full main suite 4,320 OK / 30 expected skips;
  catalog zero delta `blocked-catalog-026-master-ui` (151/151
  loaded, 0 load errors, 117,809 total / 116,756 supported /
  1,053 blocked, zero delta vs `blocked-catalog-026-live-target`);
  feature matrix unchanged (42/42, 7,475/7,475 over
  `w4b4-case30-20261020081722Z`); AP-11 0/6,143. VERSION bumped to
  0.26 with the changelog entry in the same change. The 0.26 build
  `native-20261103T112811Z-59a6b3d5` was cut from `main` @ `c114ec2`
  (2026-11-03): in-build suite 4,320 OK / 30 expected skips,
  `ce_inputs: []`, `runtime_unverified` deliberately kept per gate;
  source ZIP `CT2Trainer-0.26-source.zip` sha256
  `3d62f80cdfb95d8439d4a2f2150002976795faad313fa75d47aeb4fb92bb49bd`
  (14,348,462 bytes), portable ZIP
  `CT2Trainer-0.26-windows-portable.zip` sha256
  `49be1d286999ed175737edb073c5ab83533c40cccc7e636685a256a0b07004b3`
  (49,653,968 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `895f937ed5c228c09b97edba28aa9dc4ad228abd58585f73080f40ab265bc031`,
  16,925,677 bytes, ships next to the converter).

**0.25 content on main (2026-11-02, root-direct on `main`): Master
Trainer user control MT-10/11/12 (user request 2026-11-02).** The
Master Trainer now gives the user explicit control over which table
loads and which process attaches - and lets the user detach and
re-attach on demand. The feature set was evaluated against online
all-in-one trainer front ends (OpenForge (openforge-aio), the CE 7.5
process picker as a local read-only behavior reference,
LaunchForge/auto-update loaders); the evaluation is recorded in
`src/ct2trainer/native/master_trainer/ROADMAP.md` ("Online feature
evaluation (2026-11-02)"). Adopted: MT-10/11/12. Deliberately
deferred (documented): global per-feature hotkeys, auto-update
(offline/hash-verified build policy), and concurrent multi-table
sessions (documented single-session model).

- **MT-10 (explicit table load):** a "Load table" header button in
  the waiting view and a per-row "Load this table" context menu.
  The table loads even while the bound process is not running yet
  (the plan compiles statically; the engine waits for the process to
  start). The last explicitly loaded table persists in the state
  home (`master-settings.json` schema 2, `last_table`) and is visible
  in the metadata line. `orchestrator.request_load()` carries stable
  named refusals (`not-in-index` / `table-unreadable` /
  `no-process-binding` / `process-snapshot-failed`): a refused load
  shows a named dialog + status line and never crashes; an explicit
  load bypasses the auto-load loop guard, but a failed explicit load
  still records the ordinary (name, PID) suppression.
- **MT-11 (process selection + persisted attach mode):** new
  `process_picker.py` - a pure decision layer (`candidate_processes`,
  `attach_decision` -> attach-direct / pick / wait,
  `make_pinned_memory_factory` - the injected factory honors the
  session PID pin, self-clears the pin once that PID exits, and
  falls back to the ordinary smallest-PID name-based attach). Attach
  modes: "auto" (default, legacy behavior - no picker, smallest PID)
  and "ask" (the process picker, one row per running candidate
  name + PID, is shown for every attach, even a single candidate).
  The "Attach: auto/ask" toggle button persists the mode
  (`master-settings.json` schema 2; schema-1 documents promote on
  load with the documented defaults `last_table=null`,
  `attach_mode="auto"`). Cancel semantics per origin: an auto-load
  pick defers the exact (name, PID) pair (Retry load re-arms), a
  table choice defers exactly like "Not now", an explicit load
  returns to the waiting status, and an attach after detach stays
  paused.
- **MT-12 (detach / user attach):** engine `pause_attach()` /
  `resume_attach()` / `attach_paused` - while paused the poll attach
  branch is gated (status "Detached; waiting for user attach", no
  attach attempts, session state/journals/wishes untouched; debug
  events `attach-paused` / `attach-resumed`; pausing refused with a
  named error while closed/blocked/busy). The new "Detach"/"Attach"
  header button exists in Master mode only (the standalone trainer
  header stays byte-identical; `TrainerWindow` gains the optional
  `detach_cb`). On "Attach": "ask" mode with running candidates
  opens the process picker (origin "attach") and the chosen PID
  pins the session, then the hold resumes; "auto" mode simply
  resumes the ordinary wait. A target exit while attached is
  unaffected.
- **Tcl test-harness hardening (test-only change, no product code
  change):** new `tests/native_tk_teardown.py` with
  `force_root_release()` - deterministic Tk-root teardown on the
  creator thread (destroy + drop named test-side references + forced
  main-thread `gc.collect`) applied in all 7 UI test modules (17
  root creations: `test_native_master_ui.py`,
  `test_native_master_ui_mt12.py`,
  `test_native_sc2_crash_observability.py`,
  `test_native_staged_options_ui.py`, `test_native_trainer_sounds.py`,
  `test_native_ui_button.py`, `test_native_ui_row_details.py`). It
  removes the intermittent `Tcl_AsyncDelete: async handler deleted
  by the wrong thread` abort observed in the 0.25 full-suite
  non-verbose runs (2026-11-02). Mechanism (verified against the
  CPython 3.12 tkinter source + faulthandler dump): `Tk.destroy()`
  destroys the toplevel window and deletes the widgets' Tcl
  commands, but the underlying Tcl interpreter (the `_tkinter`
  Tkapp behind `root.tk`) is only released when the Python Tk
  object is deallocated; the root/interpreter reference cycle (the
  `after` poll callback and button commands hold bound methods
  inside the interpreter; the bound methods hold the window; the
  children/master bookkeeping holds the root) survives until the
  next cyclic GC, which runs on whatever thread allocates; when a
  worker thread's GC cycle finalizes the interpreter, Tcl aborts the
  process off the creator thread. The fault dump showed the fatal
  thread as a freshly started thread running the GC collector while
  the main test thread was mid NASM assembly in
  `test_native_record_hotkeys`. Evidence: two full-suite
  non-verbose runs aborted with the Tcl fatal (exit 1, no summary,
  ~71% position); the verbose full run completed green (Ran 4258,
  OK, skipped=30); a middle-set repro (`test_native_master_ui` +
  `test_native_master_ui_mt12` + `test_native_os_hotkeys` +
  `test_native_rearm` + `test_native_record_hotkeys`, x10) did not
  reproduce; a clean-tree (0.24 @ `aba8b65`) full run completed
  without the Tcl fatal.
- **In-build reliability fix:** the first 0.25 in-build suite run
  (`native-20261102T181843Z-ddfb63f0`, 2026-11-02; 4,259 ran, 1
  error, the rest green) exposed a state-home dependence: the
  `run_master` cancel test read the machine's real state home (the
  in-build suite runs without the LOCALAPPDATA isolation of local
  dev runs) and, on a field-tested box with a stored `last_folder`,
  took the stored-folder reuse path with the mocked `tk.Tk`. Fixed:
  the test now uses an isolated state home, a new deterministic test
  covers the stored-folder reuse path, and the waiting-view status
  variable plus the table-picker selection variable in `master_ui.py`
  carry an explicit master (the window root) instead of relying on
  the tkinter default-root lifecycle.
- **Evidence:** +66 tests (`tests/test_native_master_process_picker.py`
  16, `tests/test_native_master_explicit_load.py` 13,
  `tests/test_native_attach_pause.py` 5,
  `tests/test_native_master_ui_mt12.py` 24, +7 schema-2 tests in
  `tests/test_native_master_state.py`, +1 state-home isolation test
  in `tests/test_native_master_ui.py`); full main suite
  **4,259 OK / 30 expected skips** (2026-11-02); catalog remeasure
  `blocked-catalog-025-master-ui` (chunked 64x3 audit over the 151
  reference tables, 2026-11-02): 151/151 loaded, 0 load errors,
  117,809 total / 116,756 supported / 60,161 staged / 103,607
  actionable / 12,974 headings / 1,053 blocked - **zero delta** vs
  `blocked-catalog-024-sounds` (per-table count/reason/sha changes:
  0). Feature matrix unchanged (42/42, 7,475/7,475 over
  `w4b4-case30-20261020081722Z`); AP-11 0/6,143. VERSION 0.25 +
  CHANGELOG 0.25 entry in the same change (root-direct on `main`,
  versioning rule). The 0.25 build
  `native-20261103T062439Z-f4c16be9` (cut from `main` @ `a861bfb`,
  2026-11-03; in-build suite 4,259 OK / 30 expected skips,
  `ce_inputs: []`, `runtime_unverified` deliberately kept per gate)
  is the latest verified release; superseded 0.24 (build
  `native-20261102T102029Z-fe358e35`).

**0.23 Master Trainer roadmap complete (2026-11-01, branch
`native-0.23-master-roadmap` @ `b2d0344` + load-gate branch
`native-0.23-load-gate` @ `98a9226`; `main` @ `6e3ec98`; released in
build `native-20261101T145310Z-a160bae4`):** the remaining roadmap
items MT-6/MT-7/MT-8/MT-9 landed (two lane subagents + root
integration + the load-gate cycle), together with the waiting-view
observability work and the ask-on-first-start table-folder
parameter. No new trainer functionality - the Master stays a wrapper
around the tested engine.

- **MT-8 (frozen Master entry point):** `tools/native_master.py`
  frozen to `CT2Trainer-Master.exe` with the user-provided
  `Master_Trainer.ico` (windowed; lazy `master_ui` import so
  `--help` and the named exit-2 refusals never require tkinter; CLI
  mirrors the `master` subcommand). `build()` freezes it after the
  converter (no `CT2BASE1` marker - templates are converter-only),
  runs the CE-content `inventory()` scan, adds it to
  `payload-inventory.json`, the `build.json` outputs and the
  portable ZIP next to the converter - **the Master Trainer is now
  part of every build** (`scripts/Build-Native.ps1` unchanged: its
  single `build()` call emits the new EXE + ZIP entry). +8 tests.
- **MT-6 (per-table settings sidecar):** `settings_sidecar.py`
  `MasterSettingsStore` keyed by the table content sha256 (never by
  path), layout `<state home>/settings/<sha>.ct2trainer.json`;
  `load_for` returns `(document, [])` / `(None, reasons)` - absent
  file is normal, `SettingsRejection` reasons pass through
  displayable (never a silent reset to defaults), structural
  `SettingsError` named; `save_for` derives the known-id set from
  the document and refuses an all-empty draft with the named
  `nothing to persist`; reuses the tested `SettingsModel` unchanged.
  UI wiring: restore on load (a refused stored document is shown
  with its named reasons; the session continues without it), save on
  close (back-to-Master and window close). The on/off wish
  persistence itself stays on the engine state store (MT-4). +17
  sidecar tests, +2 UI wiring tests.
- **MT-7 (SteamOS / CheatDeck target route, documented-route scope):**
  `steamdeck_route.py` `AttachRoute` + `attach_gate` /
  `require_engine_attach` / `route_text`; Windows -> attach
  available through the unchanged native engine path; Linux/other ->
  named `DeckAttachUnavailableError` carrying the documented route
  (Proton-wrapped standalone CT2Trainer Windows trainer EXE,
  CheatDeck-compatible; the Linux/SteamOS Master runs detection +
  table index + waiting UI only; the owned Linux attach backend
  remains a later work item). The gate runs before any engine
  creation (a refusal fails the load through the orchestrator's
  named loop guard); the waiting view shows the route hint
  permanently on non-Windows. Deliberately NOT a Linux attach
  backend - the real Deck protocol run with exact build hashes stays
  root/user field work (`tests/deck/compatibility-matrix.md`). +13
  route tests, +3 UI wiring tests.
- **Waiting-view observability:** the waiting view now shows a
  compact metadata line (table counts, bound process names, last
  scan time, the state home location) and a live "Running now" line
  (bound processes visible in the latest snapshot, with PIDs);
  table rows for a running process are marked `running (PID n)`;
  `TickOutcome.running` carries the live bound-process list from the
  orchestrator tick (stable name/PID order on every tick path). +6
  orchestrator tests, +5 UI tests.
- **Ask on first start for the table folder** (CT source directory
  parameter): an explicit folder argument (CLI or frozen EXE)
  always wins; without one, the last-used folder persisted in the
  state home (`master-settings.json`, new checksum-bound
  `master_state.py` module with named `MasterStateRefusal` and
  tolerant load) is reused when it still exists; only a genuinely
  first start (or a stale stored folder) shows the directory
  picker. +15 tests, +3 UI tests.
- **MT-9 (load-time table compatibility & size gate,
  `master_trainer/table_gate.py`):** before any compile, the load
  re-proves the table file against its index entry - missing / not a
  regular file / stat-or-read failure / empty / over the 32 MiB load
  limit (33,554,432 bytes) / changed since the last scan (named
  stale refusal; Rescan re-arms) / not loadable by the tested
  `read_table` parser (malformed XML, DTD/entity input, unparseable
  legacy binary) / changed during analysis. Every refusal is a
  stable named code + displayable detail, cheapest-first; the
  default plan compiler raises the named `TableLoadGateRefusal`, so
  a table load failure is graceful even when the target process was
  found: no crash, named dialog + status line, the fail-closed loop
  guard records the exact (name, PID) pair (no hot-retry), Rescan /
  Retry load re-arm, and the picker is not re-issued for a failed
  pair. +16 gate tests, +2 orchestrator, +4 UI.
- **Same-day field fixes in the 0.23 content** (merged to `main`
  after the MT-9 merge): placeholder headings no longer create
  plan-level symbol dependencies (`28c9b57`, +10 tests - the
  WP-32/WP-33 non-actionable placeholder display-address requires are
  display metadata, never runtime writes) and the Sinking City 2
  hotkey-bridge field fix (0.22.1 lane: T1 named missing-export
  guard, T2 engine containment of bridge faults as deduped named
  warnings, T3 loop-thread close protocol, T7 persistence ordering;
  merge `4e9b95b`, +11 tests) - the fix for the SC2 0.19
  hotkey-bridge findings deferred in the 0.22 field cycle.
- Suite: +115 tests (4,061 -> 4,176); catalog zero delta across all
  three 0.23 remeasures (`blocked-catalog-023-master-roadmap` @
  `b2d0344`, `blocked-catalog-023-load-gate` @ `98a9226`,
  `blocked-catalog-023-field-fixes` @ `4e9b95b`, all 2026-11-01:
  151/151 loaded, 0 compile errors, 117,809 total / 116,756
  supported / 60,161 staged / 1,053 blocked / 0 load errors;
  per-table count and reason changes: 0).
- **Build record:** 0.23 shipped as build
  `native-20261101T145310Z-a160bae4` (cut from `main` @ `6e3ec98`,
  2026-11-01, canonical path; in-build suite 4,176 OK / 30 expected
  skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per
  gate; source ZIP `CT2Trainer-0.23-source.zip` sha256
  `3360cab031cb1334dda71bb02a511170a9a70d1f583b5a8721624f46e24da464`
  (14,291,040 bytes), portable ZIP
  `CT2Trainer-0.23-windows-portable.zip` sha256
  `eec023ba09e8fcb80608736896f0477f4a783034046e6ad67514e96ed0a2905b`
  (49,609,916 bytes); the frozen `CT2Trainer-Master.exe` (sha256
  `e5822f688c653242a9f64bd92e4ba92529d485b89c11607cf20d32e728ca3c20`,
  16,895,048 bytes) ships in the run folder, the payload inventory
  and the portable ZIP next to the converter; the source ZIP carries
  `table_gate.py` + `tests/test_native_master_table_gate.py` and the
  final 0.23 changelog entry).

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
| Independently built product | The 0.23 source and Windows portable ZIPs passed the offline build (build `native-20261101T145310Z-a160bae4`) with **4,176 tests OK, 30 expected skips**, and `ce_inputs: []`; the MT-9 gate tests + the placeholder-heading / SC2 hotkey-bridge field-fix test files + the 0.23 changelog entry ship in the source ZIP; the `master_trainer` subpackage + user-provided `Master_Trainer` icons ship in the source ZIP, and the frozen `CT2Trainer-Master.exe` ships in the portable ZIP next to the converter; the 0.20/0.20.1 branding icons remain embedded in the frozen converter EXE and the generated-trainer template EXE (verified by PE icon-resource extraction against the committed ICOs). | Keep the clean-room build and release checks green after each change. |
| Master Trainer (released in 0.21; roadmap complete in the 0.23 release; user control MT-10/11/12 as 0.25 content on main) | Full MT-1..MT-12 feature set on `main` (branch `native-0.20-master-trainer` merged at `9a725a8`; branch `native-0.23-master-roadmap` merged at `b2d0344`; load-gate branch `native-0.23-load-gate` merged at `98a9226`): incremental table index (folder + sub-folders, sha256-bound JSON in the state home, foreign-schema/tamper refusal), cross-platform read-only process watch, pure orchestrator (unique-match auto-load, multi-table picker, fail-closed loop guard, live `running` tick feedback, no picker re-issue for a failed pair), waiting UI (metadata line, live "Running now" line, running/PID tree markers) + handoff into the exact standalone trainer with `master_back`, per-table on/off persistence via the engine state store, MT-6 per-table settings sidecar keyed by table content sha256 (restore-on-load / save-on-close, named refusals), MT-7 documented SteamOS/CheatDeck target route (named fail-closed non-Windows attach refusals; NOT a Linux attach backend), MT-8 frozen `CT2Trainer-Master.exe` in every build, MT-9 load-time table compatibility & size gate (stable named refusals, graceful named load failure even when the target process was found, no hot-retry, Rescan / Retry re-arm), ask-on-first-start table-folder parameter (`master-settings.json` in the state home; explicit folder argument wins), `master` CLI subcommand, `Master_Trainer` icon contract. 306 master-trainer tests; full main suite 4,176 OK / 30 expected skips; catalog zero delta `blocked-catalog-023-field-fixes` (all three 0.23 remeasures). 0.25 content on main (2026-11-02, root-direct): MT-10 explicit table load, MT-11 process picker + persisted attach mode, MT-12 detach / user attach (details in the 0.25 section above); online feature evaluation record in `master_trainer/ROADMAP.md` (MT-10/11/12 adopted; global hotkeys / auto-update / concurrent multi-table sessions deliberately deferred); Tcl test-harness hardening (test-only `tests/native_tk_teardown.py`); in-build reliability fix (state-home isolation in the `run_master` cancel test + explicit-master Tk variables in `master_ui.py`; first in-build run `native-20261102T181843Z-ddfb63f0` exposed the dependence). 372 master-trainer tests (306 + 66: 16 process picker + 13 explicit load + 5 attach pause + 24 master UI MT-12 + 7 schema-2 + 1 state-home isolation); full main suite 4,259 OK / 30 expected skips; catalog zero delta `blocked-catalog-025-master-ui` (vs `blocked-catalog-024-sounds`). | User field test of the 0.25 content (explicit table load / process picker / detach; the 0.25 build is pending cut - 0.24 remains the latest verified build); MT-7 owned Linux attach backend + the real Deck protocol run with exact build hashes (root/user field work). |
| Synthetic feature coverage | **42/42** declared feature classes and **7,475/7,475** action weight covered across **30 synthetic tables**. | This metric does not establish support for every original table or a real game effect. Add synthetic cases when a new behavior is found. |
| Original reference tables | All **151/151** table paths load after the RT-3 legacy-binary CT loader (2026-10-23). Local static catalog (0.21 RT-5 item B/E remeasure, run `blocked-catalog-020-rt5-be`, 2026-10-31, frozen manifest `gap_inventory/reference-manifest.json`; +175 supported vs `blocked-catalog-020-icons` - the 175 `CodeEntry` records of the 22 CheatCodes tables now `code_patch` plan rows, zero newly blocked, zero reason changes) classifies **116,756 supported**, including **60,161 staged**, out of **117,809 plan entries**. | **1,053 entries are blocked** (was 1,351 after RT-4.3, 1,743 after RT-4.5, 1,778 after RT-4.6, 1,807 after RT-4.4, 1,858 after RT-4.1/RT-3 and 2,698 before RT-4.1; RT-4.2 cleared the last 298 rows - R4 Lua-runtime symbol providers re-staged, R7 GetAsyncKeyState bare calls, keep-first scope fallback; zero newly blocked). The 0.19 field-fix cycle changed no catalog row (no corpus table uses `moAlwaysHideChildren`). RT-5 item B (0.21) added exactly 175 supported `code_patch` rows with no blocked or staged movement; item E is runtime-only (zero catalog delta). Staged entries still need their runtime conditions proved. |
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
   Remaining: none — RT-5 item B (CheatCodes code-patch plan path,
   merge `9ef4a74`) and item E (`messageDialog` safe logged no-op,
   merge `b8bb4ee`) landed 2026-10-31, closing RT-5 in full (all
   inventory items A, B, C, C2, D, E, F, G landed; catalog
   `blocked-catalog-020-rt5-be`: 1,053 blocked of 117,809).
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
