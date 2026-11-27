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
(build `native-20261105T080853Z-2e7f50a5`). 0.33 released (build
`native-20261108T200230Z-b0167049` cut from `main` @ `6e71739`,
2026-11-08): the Master Trainer table folder
auto-rescan (MT-25: the waiting view re-runs the existing
incremental scan every 30 s while the persisted "Auto-rescan: on"
status-bar toggle is on - added / changed / removed tables show up
without a manual F5; the same (size, mtime_ns) + sha256 short-circuit
contract as the manual Rescan, one stat pass per interval, polling
only (no OS file-watcher), paused on trainer entry; the interval clock
restarts on a manual rescan, a folder change, and the waiting-view
rebuild; zero load-path effect - the MT-9 gate re-checks the table
independently at load time; master-state schema 6 -> 7, auto_rescan,
default on); +16 tests, full main suite 4,499 OK / 30 expected
skips, catalog zero delta `blocked-catalog-033-auto-rescan`;
in-build suite 4,499 OK / 30 expected skips, `ce_inputs: []`,
`runtime_unverified` deliberately kept per gate; source ZIP
`CT2Trainer-0.33-source.zip` sha256
`4528d1d0f2ee269fb2ee7ec470d9e9711b3c284bffe6cf582f7dafa7431756f2`
(14,433,388 bytes) - carries the MT-25 auto-rescan
(`master_state.py` schema 7, the 30 s auto-rescan tick,
`tests/test_native_master_ui_mt25.py`) and the reviewable
`master_trainer/UI.md` - and portable ZIP
`CT2Trainer-0.33-windows-portable.zip` sha256
`5e0244791b6f31a2e2219d5c33541c978ca4c0d399c8e7a234cb0c16e8ccb3d7`
(49,703,149 bytes; the frozen `CT2Trainer-Master.exe` (sha256
`59961d511d3964b075c968a3c577117ffa235970d65976f66d7e34e0eae010a9`,
16,968,879 bytes) ships next to the converter); superseded 0.32
(build `native-20261108T100731Z-a1d311e5` cut from `main` @
`bfcc3a3`, 2026-11-08). 0.43 released (build `native-20261111T184600Z-3bf9d8aa` cut from `main` @ `0df2607`, 2026-11-11): the Master Trainer minimize-to-tray + window-geometry persistence (MT-32: the persisted "Minimize to tray" toggle (master-state schema 9 -> 10, `tray_minimize`) drives the Win32 tray icon behind a bounded, named fail-closed guard - a missing `Shell_NotifyIconW` export or a refused `RegisterClassExW` (Win32 87) is the named `tray-platform-unavailable` / `tray-icon-missing` / `tray-setup-failed` refusal in the status line, never a crash and never a dialog; restore on tray double-click; the tray balloon reports the trainer's attach success / failure through the new `ui.py` `attach_observer` - the standalone trainer header stays byte-identical; MT-33: window size / position persisted in the same master-state document (`window_geometry`), saved on the bounded `<Configure>` cadence and on close, an invalid persisted geometry is the named `window-geometry-invalid` refusal) + the TGC field fix (transient target-memory reads no longer block the engine - Win32 299 joins the bounded snapshot transient retry set, the transient set {299, 119, 1116, 24} is never treated as an observed change, a real mismatch or a non-transient error blocks immediately, the bounded verify-skip streak limit of 30 ticks names the condition instead of looping; the MT-9 gate re-checks the table independently at load time); +85 tests, full main suite 5,011 OK / 36 expected skips, catalog zero delta `blocked-catalog-043-tgc` (117,809 total / 117,272 supported / 12,974 headings / 104,123 actionable / 537 blocked - zero newly blocked, zero unblocked, zero reason changes); in-build suite 5,011 OK / 36 expected skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per gate; source ZIP `CT2Trainer-0.43-source.zip` sha256 `c0011d10a5a60b78067b0cdd1a622a134088fee325ac4d544efd3ec8101438ca` (14,617,762 bytes) - carries the MT-32/MT-33 tray + geometry (`master_trainer/tray.py` + `master_trainer/window_geometry.py` + `tests/test_native_master_tray_geometry.py`) and the TGC field fix (`memory.py` + `engine.py` + `hooks.py` + `tests/test_native_tgc_field_fix.py`) - and portable ZIP `CT2Trainer-0.43-windows-portable.zip` sha256 `dc7a4062b56be99ea887a77ffd23e7c2c1ff38935e471d7f124ed4d775a022e9` (49,849,139 bytes; the frozen `CT2Trainer-Master.exe` (sha256 `4846d7568ef4eba091261b21e678c13ab5cecbbf3468a0a57ba30d84fc7e91a4`, 17,072,494 bytes) ships next to the converter). Post-0.43 (2026-11-12): the deferred compatibility-lane cycle against the 537-blocked census started - Lane C (roadmap class d: the `BaseAddress` user-symbol import proof, tests only, +9 tests in `tests/test_native_baseaddress_import.py`) merged into `main` as `7d92482`: full main suite 5,020 OK / 36 expected skips, catalog zero delta `blocked-catalog-lane-c` (117,809 total / 117,272 supported / 537 blocked - 0 newly blocked, 0 unblocked, 0 reason changes): the 80 `BaseAddress` rows of the five UE5 script-template tables (16 per table) are proven fully supported - not staged, static UDS address, `requires=['BaseAddress']` - once the user imports the symbol through the documented `<UserdefinedSymbols>` path, byte-exact through the engine, while the as-is rows keep the exact named class-d block (by design; the block message names the remedy); Lane A (Witcher3 / GoW dynamic Lua symbol registration, 182 rows) merged into `main` as `ff6e8d6` (2026-11-12): full main suite 5,036 OK / 36 expected skips, catalog remeasure `blocked-catalog-lane-a` 117,809 total / 117,454 supported / 12,974 headings / 104,305 actionable / 355 blocked (-182 vs `blocked-catalog-lane-c`, zero newly blocked, zero reason changes; exactly the 3 Lane A tables changed - GoW 32 -> 0, Witcher3 4.03 77 -> 1, Witcher3 4.02HF1 75 -> 1, each Witcher3 table keeping its single `createthread` RT-5G residual, blocked by design); Lane B (Octopath2 relative-address staging, 134 rows) merged into `main` as `285fb8a` (2026-11-12): full main suite 5,049 OK / 36 expected skips, catalog remeasure `blocked-catalog-lane-b` 117,809 total / 117,588 supported / 12,974 headings / 104,439 actionable / 221 blocked (-134 vs `blocked-catalog-lane-a`, zero newly blocked, zero reason changes; 3-chunk record-level delta: exactly the 1 Octopath2 table changed - 134 -> 0, all the "Relative address cannot skip an addressless script/value ancestor." rows staged, the other 150 tables byte-identical): the staging walk now folds relative ancestors with offset-carrying levels and index-times-stride own literals (`+00*04`) through the deterministic synthetic symbol `__ct2_rtbase_<anchor_id>` (plan metadata, never a dependency; the engine injects the anchor heading's live base per activation call, a registered symbol under the placeholder name is the named fail-closed collision); the byte-stable flat signed-hex total is kept while every level is a plain-hex relative literal with no pointer offsets anywhere, addressless headings with pointer offsets keep their byte-for-byte ambiguous-base refusal, and the Death Stranding 2 / The Sinking City plan entries are byte-identical against the pre-lane main; with Lane B all three lead cases of the 537-row census (Lane A 182, Lane B 134, Lane C 80 by design) are closed. 0.44 released (build `native-20261112T233337Z-1dc678c6` cut from `main` @ `ab11893`, 2026-11-13): the deferred compatibility-lane cycle shipped as the 0.44 release - catalog remeasure `blocked-catalog-lane-b` 117,809 total / 117,588 supported / 12,974 headings / 104,439 actionable / 221 blocked (net -316 vs `blocked-catalog-043-tgc`: 182 + 134 unblocked, zero newly blocked, zero reason changes, exactly the 4 lane tables changed, the other 147 byte-identical); full main suite 5,049 OK / 36 expected skips; in-build suite 5,049 OK / 36 expected skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per gate; source ZIP `CT2Trainer-0.44-source.zip` sha256 `026886a700282a56c40568f30d2a4ebc57d6390a59cd59c42fd3f7f5dc8d49ff` (14,648,668 bytes) - carries the three-lane cycle (`tests/test_native_baseaddress_import.py`, `lua_program.py` + `lua_symbol_providers.py` + the two lane A test files, `compiler.py` + `engine.py` + `tests/test_native_staged_pointer_chain.py`) - and portable ZIP `CT2Trainer-0.44-windows-portable.zip` sha256 `656bf7106fd86a5a21532cf476b91f82cfafe2287ef5bf3d3ba41b6d2d9d6f36` (49,885,729 bytes; the frozen `CT2Trainer-Master.exe` (sha256 `02e4731ef30ce320f71594f37cb176402be64849a90656c785d474dbc50d6112`, 17,084,284 bytes) ships next to the converter); the remaining 221 blocked rows are the documented design / gate residuals. 0.45 released (build `native-20261113T144426Z-572d5b30` cut from `main` @ `58d6c8f`, 2026-11-13): the per-session hotkey switch (MT-34, the WeMod QoL from the 0.43 candidate list) + the trainer-tick-sound field fix - the trainer header gains "Hotkeys: on/off" in every trainer (standalone + Master, like Re-attach): off releases every published hotkey binding for the session (model controller + OS bridge mirror reconciled to an empty live set, nothing new published), on re-publishes the table-declared hotkeys of the live records (the table's defaults - no per-record override surface); the plan-level bindings are never mutated, the state is session-scoped and never persisted, the ordinary toggle / dispatch paths stay fully functional while off, `hotkeys-session-switched` debug event; the 0.24 tick sounds were silently dead in the field - the stdlib winsound PlaySound wrapper raises RuntimeError("Cannot play asynchronously from memory") for SND_MEMORY | SND_ASYNC - playback now goes through winmm.PlaySoundW directly via ctypes (house attribute-access binding pattern, one persistent buffer per kind, named refusals "winmm unavailable" / "PlaySoundW failed (Win32 <code>)", live-verified all three kinds play); +13 tests (new `tests/test_native_hotkey_session_switch.py`, reworked `tests/test_native_trainer_sounds.py` PlaybackTests), full main suite 5,062 OK / 36 expected skips, catalog zero delta (117,809 total / 117,588 supported / 12,974 headings / 104,439 actionable / 221 blocked - MT-34 and the sound fix touch no table-parsing path); in-build suite 5,062 OK / 36 expected skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per gate; source ZIP `CT2Trainer-0.45-source.zip` sha256 `3bdd783359623d273de15e90f4f0acc524d3ecbda64f925c3cf59de9d4e27416` (14,657,388 bytes) - carries MT-34 (`engine.py` + `ui.py` + `tests/test_native_hotkey_session_switch.py`) and the sound fix (`trainer_sounds.py` + `tests/test_native_trainer_sounds.py`) - and portable ZIP `CT2Trainer-0.45-windows-portable.zip` sha256 `58bac73098b219e3049668b55877e8a3e4fd758e6e1917b058da128e416eb4e2` (49,854,120 bytes; the frozen `CT2Trainer-Master.exe` (sha256 `f882add64b2fc0f9d66cb88ed2142684e71736de326b28f72ddb007186aa2d05`, 17,069,125 bytes) ships next to the converter). 0.46 released (build `native-20261113T185658Z-e543af1a` cut from `main` @ `b348184`, 2026-11-13): the AA extended-register `l` alias + `dqword` size-keyword parity (the compatibility lane against the 221-row post-0.44 census - CE `getreg` accepts the `l` 32-bit alias R8L..R15L and CE `dqword` is the 128-bit size, the pinned NASM accepts neither; recognition - `r8l`..`r15l` join the register set, `dqword` the size-keyword set - plus `_CE_TO_NASM_SPELLING` normalization to `rXd` / `oword`, byte-identical through the pinned NASM); +9 tests, full main suite 5,071 OK / 36 expected skips, catalog remeasure `blocked-catalog-046-regsize` 117,809 total / 117,599 supported / 12,974 headings / 104,450 actionable / 210 blocked (net -11 vs `blocked-catalog-lane-b`: the 9 direct register / size rows + 2 provider cascades unblocked, zero newly blocked, zero reason changes); in-build suite 5,071 OK / 36 expected skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per gate; source ZIP `CT2Trainer-0.46-source.zip` sha256 `c49323d56d8feab0652f676d86a739fb6204cff6ddeed8e4b326e43020ee4d62` (14,661,247 bytes) - carries the register / size parity lane (`aa_program.py` + `tests/test_native_aa_register_aliases.py`) - and portable ZIP `CT2Trainer-0.46-windows-portable.zip` sha256 `1b130db71508e42b98c4127ebcec766bc79cd65aabdd563ed59d4b058bfc9fe9` (49,857,331 bytes; the frozen `CT2Trainer-Master.exe` (sha256 `18306034231d6632ba15f4f23f62e611dd2c9b73e14db634d99f6cdccb7e8857`, 17,069,499 bytes) ships next to the converter); superseded 0.45 (build `native-20261113T144426Z-572d5b30`). 0.47 released (build `native-20261114T011046Z-ee5cecee` cut from `main` @ `6e1940e`, 2026-11-14): the optional code signing for the frozen and generated trainer executables (the Smart App Control handling - the field block observed 2026-11-14 on the 0.46 trainer: SAC refuses unsigned binaries by hash, has no per-app allow and is a one-way off on Win11; the durable fix is an Authenticode signature from a trusted-CA code-signing certificate): the new pure `code_signing.py` layer (env-only config `CT2TRAINER_SIGN_PFX` / `CT2TRAINER_SIGN_PFX_PASSWORD` / `CT2TRAINER_SIGNTOOL` / `CT2TRAINER_SIGN_TIMESTAMP_URL`, never persisted; signtool `sign /v /f <pfx> [/p <pwd>] /fd SHA256 [/tr <url> /td SHA256]` with the bounded 300 s timeout; the pure PE security-directory `certificate_table` walk re-proving the WIN_CERTIFICATE revision 0x0200 / type 0x0001 / declared length after a reported success; fail-closed named refusals `sign-not-win32` / `sign-signtool-unavailable` / `sign-certificate-missing` / `sign-failed` / `sign-verification-failed` - a configured signing that fails never ships an unsigned binary) wired into `tools/native_build.py` (converter + master signed after freezing, the template stub deliberately unsigned - a certificate table after its CT2BASE1 trailer would break the converter's template check; build.json `code_signing` facts) and into `bundle.build_trainer` (every generated trainer signed before publication through the injectable `sign` seam; the trainer `.build.json` gains the `signed` flag); `bundle.read_embedded_plan` no longer assumes the footer at EOF - a bounded backwards `CT2NATV1` magic scan (1 MiB certificate-tail window) where every candidate is proved against the plan checksum, so the plan survives the certificate table signtool appends after the footer; without `CT2TRAINER_SIGN_PFX` nothing is signed and every produced byte is identical to the unsigned flow (this build: `code_signing.converter/master signed: false, reason: not-configured`); +37 tests (new `tests/test_native_code_signing.py` 32 + `tests/test_native_bundle.py` +5), full main suite 5,108 OK / 36 expected skips, catalog delta none (no table-parsing path touched - 117,809 total / 117,599 supported / 210 blocked unchanged); in-build suite 5,108 OK / 36 expected skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per gate; source ZIP `CT2Trainer-0.47-source.zip` sha256 `436a330aeceb70a51c2fc5585085a133b25ea6f05aedcdfa25353aa9042d436d` (14,675,788 bytes) - carries the code-signing package (`code_signing.py` + `tests/test_native_code_signing.py` + the bundle footer-scan) and the SAC user docs (`usage.md` section 8, `build.md` section 3) - and portable ZIP `CT2Trainer-0.47-windows-portable.zip` sha256 `146ee9cd99a12865779ba1daff9e66fa0855be20a7a847d0bd47a513e74bc3a5` (49,879,105 bytes; the frozen `CT2Trainer-Master.exe` (sha256 `a770f9689a5744a49aa26ec911437f0fcd09a05631e85edcfea92061b6658453`, 17,066,832 bytes) ships next to the converter); the signed build path still needs a user-supplied trusted-CA PFX (no certificate on this machine; the self-signed option does not clear SAC). Superseded 0.46 (build `native-20261113T185658Z-e543af1a`). 0.48 released (build `native-20261114T133842Z-8ee6999f` cut from `main` @ `5d467dc`, 2026-11-14): the CE 7.5 trailing-offset parity (the compatibility lane against the 210-row post-0.47 catalog census: the four `[mats]20` / `[mats]28` value-record addresses of qt-ds-1 + qt-ds-2 (records 130674 + 130675 each, next to their supported `[mats]` / `[mats]+8` / `[mats]+10` / `[mats]+18` siblings) plus the raymanlegends_dvt `Made by` string address that stays blocked by design) - CE `TSymhandler` (symbolhandler.pas L3073-3140 tokenize, L5516-5553 `]` dereference, L5603-5655 arithmetic accumulation with `+` as the default operation) reads `[mats]20` as `[mats]+0x20` (hex default); the bounded grammar extension in `address_expression.parse_expression` gives one value atom directly after a `]` token an implicit `+` operand (explicit operators, a closing/repeating bracket, a `(` and 0x/$/#-prefixed numbers stay refused; a `[` after `]` is included; byte-stable: only previously-erroring expressions change shape); +19 tests, full main suite 5,127 OK / 36 expected skips, catalog remeasure `blocked-catalog-048-trailing` 117,809 total / 117,603 supported / 12,974 headings / 104,454 actionable / 206 blocked (net -4 vs `blocked-catalog-046-regsize`: the 4 direct qt-ds rows unblocked, zero newly blocked, zero reason changes, the other 149 tables byte-identical); in-build suite 5,127 OK / 36 expected skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per gate; source ZIP `CT2Trainer-0.48-source.zip` sha256 `feb962e5628027f1ee79acbc16cb10a4dfe36ef5a3de7f4cf4f3681d9cc37f0b` (14,682,168 bytes) - carries the trailing-offset parity lane (`address_expression.py` + `tests/test_native_trailing_offsets.py`) - and portable ZIP `CT2Trainer-0.48-windows-portable.zip` sha256 `352069d184e93f19f6ec56ce9236bedc168b09e66da7c3ac2af15b13615d3a85` (49,879,644 bytes; the frozen `CT2Trainer-Master.exe` (sha256 `9843d6dce2445af3bc883f12b9b16f6b5eb2c0fbfa2c86dae986c77c65383f10`, 17,066,255 bytes) ships next to the converter); the build ran unsigned by default (`code_signing` not-configured - no certificate on this machine, the signed path activates with a user-supplied trusted-CA PFX). Superseded 0.47 (build `native-20261114T011046Z-ee5cecee`). 0.49 released (build `native-20261114T184922Z-4b721a9e` cut from `main` @ `20c63c1`, 2026-11-14): the FO4 "Player Editor" shape-3 dynamic-variable Lua symbol provider + the remaining class-d user-symbol import ratification (tests only, against the 198-row post-0.48 catalog census) - shape 3 in `lua_symbol_providers.extract_lua_symbol_providers`: a record's `{$lua}` registers each entry under its name through a variable that ranges over a flat literal string array - the array's string constants are the record's staged provides; strictly bounded (flat string arrays only, string constants only, the exact `local var = ARRAY[i]` single-index binding with a variable index, one binding per variable, one array definition per name, same part; out of bound: row tables, numeric or identifier cells, constant indices, double-index tails, re-bound variables, unbound arrays, non-local bindings, call arguments, more than MAX_PROVIDERS derived names - every shape pinned); registration evidence from the preamble + enable lua parts, release evidence from the disable phase only (an enable-phase `unregisterSymbol(var)` is the re-entrance guard, not a deactivation release); the strict-pair / one-shot adoption rule and the MAX_PROVIDERS valve unchanged, the WP-56 spellings count; +15 tests in `tests/test_native_lua_variable_symbol_providers.py`; the ratification lane proves the documented `<UserdefinedSymbols>` import path on the 17 residual class-d value-symbol rows (6 x `g_GameLibSystemAssets` HorizonForbiddenWest, 5 x `HeroSystem` RiftApart, 3 x `pGrav` YLILWin64, 2 x `MapLastLeftClickCoordinates_Pointer` AtomicHeart v1.2, 1 Kena three-part module-qualified operand `FreeResources` + `Kena` + `Win64` - the full managed name as a single UDS does NOT cover the decomposition, the progressive remedy names the next missing part each time): every row blocked as-is with the exact named message, supported / unstaged / dependency-free with the import, byte-exact through the engine (flattened expression chains + offset-list `resolve_pointer`); the 2 `HeroHealthVFTable` rows stay out of scope (encoded embedded-Lua registration with a `createThread` entry point, not a static symbol import); +13 tests in `tests/test_native_user_symbol_import_remaining.py`; full main suite 5,155 OK / 36 expected skips, catalog remeasure `blocked-catalog-049-variable` 117,809 total / 117,611 supported / 12,974 headings / 104,462 actionable / 198 blocked (net -8 vs `blocked-catalog-048-trailing`: exactly the 8 Fallout4 "Player Editor" stat rows unblocked (Fallout4.CT ids 946-952 + 956), zero newly blocked, zero reason changes, the other 150 tables byte-identical); in-build suite 5,155 OK / 36 expected skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per gate; source ZIP `CT2Trainer-0.49-source.zip` sha256 `e2adfb4d6153d0293e1be70e43d15f71a5b8ecd6889b7ecb74ec79cc9179ce24` (14,699,553 bytes) - carries the shape-3 lane (`lua_symbol_providers.py` + `tests/test_native_lua_variable_symbol_providers.py`) and the class-d ratification (`tests/test_native_user_symbol_import_remaining.py`) - and portable ZIP `CT2Trainer-0.49-windows-portable.zip` sha256 `4139bf2079f11ca7fba8c41b1d0c1bd201d146abdd3f8171bbafa18a7a931675` (49,888,023 bytes; the frozen `CT2Trainer-Master.exe` (sha256 `d3ada53a7ebc6c160be55608046a286ba98028a1858cc2d950a64327a529d63b`, 17,070,681 bytes) ships next to the converter); the build ran unsigned by default (`code_signing` not-configured - no certificate on this machine, the signed path activates with a user-supplied trusted-CA PFX). Superseded 0.48 (build `native-20261114T133842Z-8ee6999f`). 0.50 released (build `native-20261114T223759Z-086989d6` cut from `main` @ `4f747ce`, 2026-11-14): the Provider-21 parity lane against the 21-row 'no unique supported provider' census of the post-0.49 catalog (Fix 1: CE 7.5 comment-to-EOF parity in the AA source scanners - aa_program._clean_source + aa._without_comments: an unterminated { ... } or /* ... */ block comment is stripped silently to the end of the source (CE removecomments, autoassembler.pas L732-798, read-only reference: the comment state persists to the end of the text, no error path); the quoted-string-without-closing-quote refusal stays named; a comment that swallows a section marker removes that section, so the section contract refuses the stripped program with its own named reason ('Both ENABLE and DISABLE sections are required.')); (Fix 2: CE 7.5 shared-globalalloc parity in compiler._dependencies - a compatible duplicate provider set (every declarer allocates the same shared global with the same size and flags, the shared_provider_compatible contract) now collapses keep-first instead of the ambiguity refusal: CE globalalloc (autoassembler.pas L2103-2148) reuses the existing same-process allocation by name (symbolhandler.pas L3713+ lookup-first SetUserdefinedSymbolAllocSize), GlobalPool.acquire keeps the name-keyed exact-flag contract, so every compatible declarer resolves to the identical address; the keep-first scope (provider_alternatives) covers the compatible sets, so the RT-4.2 (R3) fallback reaches them too; the 'Unselected symbol provider conflicts with the selected shared global' branch stays reachable only for full sets the compatibility check rejects) + the tests-only ratification of the 17 by-design rows (tests/test_native_provider21_ratification.py: 14 tests / 7 clusters - Cronos gun x3 (WP-37 pBase handover), Cyberpunk healthPtr x4 (the table's own $proces typo - CE fails the same row: getmodulebyname misses, the getAddressFromName fallback misses, the aobscanmodule handler aborts with rsAAModuleNotFound, autoassembler.pas L1073-1145, no $proces special case anywhere in CE), DS2 KeyHandlerThread x3 (Lua envelope prefixed handover), DS2 freecam_enabled (the g_Instance per-symbol report), DS2 InventoryItemProperties_call_dest (bare call target - the generic wording), ForgottonAnne usemono x3 (out of parity scope by design), RiftApart HeroHealthVFTable x2 (rows 1031 / 1032, provider 1030 'Modify Damage Packet' - encoded embedded-Lua out of scope, RT-5G; the static-import remedy is the counter-proof) - per cluster: the exact provider block reason + the exact dependent refusal + the counter-proof that the rows resolve once the documented condition is met); +16 tests, full main suite 5,171 OK / 36 expected skips, catalog remeasure blocked-catalog-050-provider21 117,809 total / 117,616 supported / 12,974 headings / 104,467 actionable / 193 blocked (net -5 vs blocked-catalog-049-variable: exactly the Cyberpunk2077 380/381 weaponPtr dependents + the SonicFrontiers 1337230409 'Pin Ball' provider + its 1337230410/1337230411 pPinBall dependents unblocked, zero newly blocked, zero reason changes, the other 148 tables byte-identical); in-build suite 5,171 OK / 36 expected skips, ce_inputs: [], runtime_unverified deliberately kept per gate; source ZIP CT2Trainer-0.50-source.zip sha256 79c841e9bd7978fdc954a783f7f6989b79d82da9d10a95c35e66a20b7ee6520b (14,709,622 bytes) - carries the Provider-21 parity lane (aa_program.py + aa.py + compiler.py + tests/test_native_provider21_ratification.py + the re-pins in tests/test_native_aa_named_refusals.py / tests/test_native_aa_literals.py / tests/test_native_rt42_runtime_provider.py / tests/test_native_assembler.py / tests/test_native_global_engine.py) - and portable ZIP CT2Trainer-0.50-windows-portable.zip sha256 fc89315877b0c60b53db8bde568e0c751002f0912e9ad1726f6373eb50f59187 (49,891,552 bytes; the frozen CT2Trainer-Master.exe (sha256 417708d985bfb0f84530b0fe3703aa7788db81e10e48915218fc875cf236aab6, 17,071,577 bytes) ships next to the converter); the build ran unsigned by default (code_signing not-configured - no certificate on this machine, the signed path activates with a user-supplied trusted-CA PFX). Superseded 0.49 (build `native-20261114T184922Z-4b721a9e`). 0.51 released (build `native-20261115T023110Z-4ed2835e` cut from `main` @ `35542f4`, 2026-11-15): the post-0.50 residual-census ratification lane (tests only, zero catalog delta): the five remaining unrated residual classes of the 193-row catalog census (blocked-catalog-050-provider21) are pinned as blocked by design - per cluster the exact block reason as measured in the census + the counter-proof that the rows resolve once the documented condition is met (no hidden second gate): DS2 KeyHandlerThread x11 (every record allocates the SAME symbol name through a Lua-generated alloc line and registers / releases it in the static {$asm} envelope; the static program never lists the Lua-generated allocation, so each record's own dealloc drops to unowned_cleanup_dropped and the 0.42 cleanup-parity re-check re-blocks each record with the prefixed WP-37 handover refusal, owner = first other entry in entry order; CE 7.5 breaks the same way at runtime - the later record's registersymbol overwrites the shared name, so the earlier record's disable-phase dealloc frees the later record's live thread block: the table is a one-record-at-a-time test harness), AtomicHeart-Win64-Shipping 73 (the DISABLE line unregistersymbol(energyBkp)dealloc(newmem) glues a second directive onto the first - CE consumes the line at the first directive, autoassembler.pas L2492-2525, and silently discards the glued dealloc: a leaked block, the record works), P3R-v4 229 (reassemble(moneylost_gain+4,5) - CE reassemble is single-argument, autoassembler.pas L2413-2452; counter-proof: the single-argument form), Cyberpunk2077 159 (assert(true) - CE assert requires the two-argument assert(address, bytestring) form, autoassembler.pas L2023-2030, rsWrongSyntaxASSERTAddress1122335566 for the comma-less line; the record is a debug helper whose Lua lookup runs first and whose assert then fails - broken in CE as well), TheSinkingCity Remastered 258084 (the DISABLE phase writes bFastTravel: db 0 to the record's own ENABLE globalalloc(bFastTravel,1,$process) with changed bytes - in CE the global persists session-lifetime and the line is a plain data write; the O19 shared-global contract fails closed by design because the global-pool lifecycle and recovery journal do not journal a changed re-initialization), Little Kitty, Big City 1 / 2 (usemono() on the first static envelope line targets a CE newer than 7.5 - out of parity scope by design, the Static AA envelope prefix form; counter-proof: the record without the directive); +13 tests, full main suite 5,184 OK / 36 expected skips, catalog remeasure blocked-catalog-051-residual: 117,809 total / 117,616 supported / 12,974 headings / 104,467 actionable / 193 blocked (zero delta vs blocked-catalog-050-provider21: record-level diff per table - zero count diffs, zero newly blocked, zero unblocked, zero reason changes, all 151 tables byte-identical; every remaining residual row is now covered by a documented gate or a 0.44-0.51 ratification lane); in-build suite 5,184 OK / 36 expected skips, ce_inputs: [], runtime_unverified deliberately kept per gate; source ZIP CT2Trainer-0.51-source.zip sha256 a1cc1b3eb33aca8ff7a041d999f5714a84aec238e782f396f5e6eb7385d4f525 (14,717,423 bytes) - carries the residual-census ratification lane (tests/test_native_residual_ratification.py) - and portable ZIP CT2Trainer-0.51-windows-portable.zip sha256 53923298adf229d526995274c98f3bd7476d124ca2d0fc13577392571395a675 (49,894,393 bytes; the frozen CT2Trainer-Master.exe (sha256 1dff59f006370da718ecf343e66d6cdf78ad7b462bb7468348a4dbbdeb5893bb, 17,071,049 bytes) ships next to the converter); the build ran unsigned by default (code_signing not-configured - no certificate on this machine, the signed path activates with a user-supplied trusted-CA PFX). Superseded 0.50 (build `native-20261114T223759Z-086989d6`). 0.52 released (build `native-20261115T070952Z-14405931` cut from `main` @ `26e6ebc`, 2026-11-15): the owned luacall binding + the Windows scan-fixture lane (the production `luacall_binding_factory` behind the engine's `_require_luacall_binding` gate - the owned reviewed nth-AOB helper route for records whose AA envelope carries `luaCall(...)` references: `src/ct2trainer/native/luacall_binding.py` (`OwnedNthAobPort` on the engine's attached target memory - module-bounded, 1-based occurrence, identity-checked, a bounded read-only pass - a scan never writes target memory; `OwnedLuaCallBinding` covering exactly `lua_aobscan` / `ct2trainerNthAOB`; `owned_luacall_binding_factory` wired at the standalone trainer / Master trainer / scan-gate construction sites only, engine default stays fail-closed, plans naming any other Lua function stay refused by exact name - the generic table-Lua route remains open, AP-11) + the `scan_probe.py` fixture re-pin - the owned process/nth scan gate (the second Windows function gate) verified in the source runtime (the first run failed the open luacall gate fail-closed, the new binding closed it, both the x64 and x86 reports `ct2trainer-owned-scan/v1` passed, 8/8 checks each, `ce_inputs: []`, `owned_markers_absent: true`) + the frozen scan gate re-run at the release cut on the 0.52 template (the two frozen scan trainers regenerated with the new template stub, both reports passed 8/8, plan identity identical to the source runtime); +13 tests, full main suite 5,197 OK / 36 expected skips, catalog remeasure `blocked-catalog-luacall-binding`: 117,809 total / 117,616 supported / 12,974 headings / 104,467 actionable / 193 blocked (zero delta vs `blocked-catalog-051-residual` - the binding + wiring touch no table-parsing path; the remaining 193 blocked rows are the documented design / gate residuals of the 0.51 residual census, unchanged); in-build suite 5,197 OK / 36 expected skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per gate; source ZIP `CT2Trainer-0.52-source.zip` sha256 `4ab1445befb795a40387d6ab69b0bf7b5f333b73cd62d2769b3083cab6969a7b` (14,729,777 bytes) - carries the owned luacall binding (`src/ct2trainer/native/luacall_binding.py` + `tests/test_native_luacall_binding.py`) - and portable ZIP `CT2Trainer-0.52-windows-portable.zip` sha256 `2009c3f1a959766ab793c6b6b57d89dcfb27143b4b1a8c03b78665d450fbd2cf` (49,899,983 bytes; the frozen `CT2Trainer-Master.exe` (sha256 `29f99e7a069a5a51d03b765ff40d8573684ba3567ec48f4f85fcc26722895903`, 17,072,825 bytes) ships next to the converter); the build ran unsigned by default (code_signing not-configured - no certificate on this machine, the signed path activates with a user-supplied trusted-CA PFX). Superseded 0.51 (build `native-20261115T023110Z-4ed2835e`). Superseded 0.42 released (build `native-20261111T044023Z-04112d15` cut from `main` @ `377f760`, 2026-11-11): the CE 7.5 cleanup parity (a disable-phase cleanup name that NO program owns is a silent no-op, matching CE `unregistersymbol` / `dealloc` - read-only reference: `autoassembler.pas` L2492-2525 / L2625-2669; the name is dropped from the program and recorded in the new program field `unowned_cleanup_dropped` instead of refusing the program, while a name live-registered by another supported record keeps the named WP-37 handover refusal - a plan-level re-check re-blocks a first-pass-supported record whose dropped name is a handover name or in another supported record's entry-level `provides`, with the single-form reason "Program may not unregister or deallocate the externally owned symbol X (owned by record N).") + the bounded Windows API-export registry extension (RT-4.2 R7: `sleep` / kernel32.dll, `showwindow` / user32.dll - the corpus thread idioms (HorizonForbiddenWest `call Sleep`, APlagueTaleRequiem / Resonance `call ShowWindow`) resolve with the exact `api_exports` marker + link-time PE export resolution); +9 tests, full main suite 4,926 OK / 35 expected skips, catalog remeasure `blocked-catalog-042-cleanup`: 117,809 total / 117,272 supported / 12,974 headings / 104,123 actionable / 537 blocked (-268 vs `blocked-catalog-041-digit-labels`, zero newly blocked, 268 unblocked: 26 `Sleep` + 2 `ShowWindow` + 24 direct cleanup-ownership rows + 216 provider cascades; 12 still-blocked rows carry the more specific named handover reason); in-build suite 4,926 OK / 35 expected skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per gate; source ZIP `CT2Trainer-0.42-source.zip` sha256 `f44d248303b302b8621e80efc7c6faff476d0f27887b729546bf42c639839415` (14,589,013 bytes) - carries the CE 7.5 cleanup parity (`aa_program.py` + `compiler.py` + `tests/test_native_aa_cleanup_parity.py`) and the API-export registry extension (`sleep` / `showwindow`) - and portable ZIP `CT2Trainer-0.42-windows-portable.zip` sha256 `305832ddc03487542c9a889e150b96f45c1576fa5e56819276da54b9388a5c40` (49,821,481 bytes; the frozen `CT2Trainer-Master.exe` (sha256 `35389c7611715b494418b2c5bcdbd48e84f8d55a55f3deab556c4aa4d6aefd1c`, 17,051,026 bytes) ships next to the converter); superseded 0.41 released (build `native-20261110T210856Z-5811040c` cut from `main`
@ `c724a7e`, 2026-11-10): the AA typed-constant package (the
CE `StrToQWordEx` contract) + the digit-leading-label CE 7.5
parity fix (the full typed family
`(int|float|double|dword|qword|word|byte)` as operand, data
literal and `define` value - the integer family follows the
CE `StrToQWordEx` contract: a `0x`/`$`-prefixed or pure-hex
literal parses as an integer, a decimal / exponent form
parses as a float and truncates toward zero, an out-of-range
value is the named refusal "Typed constant exceeds the
{type} representation."; the float / double family
finite-only with the named `Inf`/`-Inf`/`NaN` spellings; the
dialect boundary - typed constants parse pure digits
DECIMAL, the unsized AA dialect stays hex-by-default - 41
corpus rows byte-changing CE-parity fixes incl. the
Borderlands3 `cmp [flag],(byte)2` byte-compare, the two
decimal-form DS `(int)0.00` rows assemble for the first
time); (the `getPotentialLabels` contract - a `name:` line
is a positional label definition iff
`trystrtoint64('$'+name)` fails: the `_symbol_name_token()`
predicate at all eight cursor / symbol sites in
`aa_program.py`, digit-leading non-hex names local labels,
all-hex names the classic symbol cursor, the `0x...`
literal tokens never in the requirements, the link walk's
`key not in resolved` guard keeps the Octopath `8Path*`
scan symbols on the classic resolution path - closing the
second Death Stranding "Load Table" root, record 130605,
whose failure blocked the ~243-row "no unique supported
provider" cascade); +38 tests, full main suite 4,917 OK /
35 expected skips, catalog remeasure
`blocked-catalog-041-digit-labels`: 117,809 total /
117,004 supported / 12,974 headings / 103,855 actionable /
805 blocked (-248 vs `blocked-catalog-040-process-id`, zero
newly blocked, 248 unblocked, zero reason changes);
in-build suite 4,917 OK / 35 expected skips, `ce_inputs: []`,
`runtime_unverified` deliberately kept per gate; source ZIP
`CT2Trainer-0.41-source.zip` sha256
`05ef6cabca08adcca8a084722581b7d553966e480e28274a4a72f4b31b9c1964`
(14,580,191 bytes) - carries the AA
typed-constant package (`aa_program.py` +
`tests/test_native_aa_typed_constants.py`) and the
digit-leading-label CE 7.5 parity fix
(`tests/test_native_aa_digit_labels.py`) - and portable ZIP
`CT2Trainer-0.41-windows-portable.zip` sha256
`533bee676d0ed5c487741cb4919af8f4370f2bee1c5c26181ed5f3f0c3753a77`
(49,814,303 bytes; the frozen
`CT2Trainer-Master.exe` (sha256
`ce07c42cf22c57eeeffa08be74ff562d3a7dcfca5f4c2d14121c784acd24c6f`,
17,049,435 bytes) ships next to the converter); superseded 0.40 released (build `native-20261110T093203Z-82c49872` cut from `main`
@ `e611e9e`, 2026-11-10): the Master Trainer process
identification in picker + details (MT-31) + the bounded
zero-transfer transient-write retry in `memory.py` (MT-31: the
optional identification fields `path` / `creation_time` /
`pointer_size` on `ProcessSnapshotEntry`, all default `None`
- fail-closed, the row keeps the byte-stable name + PID
form, the `pid` / `name` decision fields are never touched;
the bounded per-candidate enrichment only at picker +
details open - Windows `OpenProcess(PROCESS_QUERY_INFORMATION)`
+ `QueryFullProcessImageNameW` + `GetProcessTimes` +
`IsWow64Process2`, procfs `exe` link target + `stat` field 22
+ `btime`; the picker rows and the table-details "Running
now" row render the proved facts, a refused fact never
renders; zero load-path effect, the MT-9 gate re-checks the
table independently at load time); (the write-side symmetry
of the 0.39 transient-read retry: a `WriteProcessMemory`
call that FAILED with the transient set {299, 119, 1116,
24} and transferred NOTHING is retried in `memory._write_checked`
with the bounded exponential backoff - exactly 4 attempts,
backoff 0.05 -> 0.25 s; a partial transfer or any
non-transient code is never retried, the original error is
raised unchanged after the budget - completing the read /
write pair); +46 tests, full main suite 4,879 OK / 35
expected skips, catalog zero delta
`blocked-catalog-040-process-id`; in-build suite 4,879 OK / 35
expected skips, `ce_inputs: []`, `runtime_unverified`
deliberately kept per gate; source ZIP
`CT2Trainer-0.40-source.zip` sha256
`46ad5dd9f9adc872e320dd4aec2362e007020ae879bba0cc8fe0621e44c34c40`
(14,569,029 bytes) - carries the MT-31 process
identification (`process_watch.py` enrichment layer +
`tests/test_native_master_ui_mt31.py`) and the bounded
transient-write retry
(`tests/test_native_memory_write_retry.py`) and the reviewable
`master_trainer/UI.md` - and portable ZIP
`CT2Trainer-0.40-windows-portable.zip` sha256
`5075586c7b0f3251749c8e3e60ec0db7fea251db39190b59b63273a4e9b10bd6`
(49,809,535 bytes; the frozen `CT2Trainer-Master.exe` (sha256
`52f6da1cebfc44a0dc791d4b5758112342b5a1d42c9fc9656901a16d1a5eb03f`,
17,048,910 bytes) ships next to the converter); superseded 0.39 (build `native-20261110T051241Z-57bf7d47` cut from `main`
@ `17a22f7`, 2026-11-10): the Master Trainer per-table auto-load
policy (MT-29) + state folder / debug log quick access (MT-30) +
the bounded transient-read retry in `memory.py` (MT-29: the
persisted per-table auto-load policy - `table-autoload.json`
schema 1 under the state home, keyed by the table content
sha256 - the same identity as the MT-24/27/28 sidecars, so a
policy survives a rename and follows a content-identical file
to another root; only the non-default manual-only policy
persists, the absence of an entry is the documented automatic
default; a manual-only table is never auto-loaded: no request,
no picker, a stable named waiting detail instead, an open
choice dropped back to waiting; the explicit MT-10 load path is
never affected; a table without a content sha cannot carry a
policy; the row context menu toggle + the MT-22 details row +
the waiting-view filter matches the persisted policy text);
(MT-30: the two master-only waiting-view header buttons "State
folder..." and "Debug log..." - one click opens the persisted
state home or the current trainer debug log in the platform
file manager / default handler; the pure `state_access.py`
layer with named `StateAccessRefusal` codes, every refusal in
the status line - never a dialog, never a crash); (the
field-observed transient "ReadProcessMemory failed (Win32
error 299)" is now retried in `memory._read_exact` with the
bounded exponential backoff - transient set {299, 119, 1116,
24}, exactly 4 attempts, backoff 0.05 -> 0.25 s; a partial
result is never retried, the original error is raised
unchanged after the budget; closing the documented open issue
of the 0.38 ledger); +73 tests, full main suite 4,833 OK / 30
expected skips, catalog zero delta
`blocked-catalog-039-autoload`; in-build suite 4,833 OK / 30
expected skips, `ce_inputs: []`, `runtime_unverified`
deliberately kept per gate; source ZIP
`CT2Trainer-0.39-source.zip` sha256
`14163e7475477c177be339d06fd5ba7b9a7016667405669b084faed25035a923`
(14,549,960 bytes) - carries the MT-29 auto-load policy
(`table_autoload.py` pure layer + `table-autoload.json`
schema 1, `tests/test_native_master_autoload.py` +
`tests/test_native_master_ui_mt29.py`), the MT-30 state folder
/ debug log quick access (`state_access.py` pure layer,
`tests/test_native_master_ui_mt30.py`) and the bounded
transient-read retry
(`tests/test_native_memory_read_retry.py`) and the reviewable
`master_trainer/UI.md` - and portable ZIP
`CT2Trainer-0.39-windows-portable.zip` sha256
`7d5d7903f1be5df0eac0f1067d5c2ca596321a41ea37381e033e5deb175ec8b6`
(49,800,752 bytes; the frozen `CT2Trainer-Master.exe` (sha256
`e0db5b2e2f41ec816089486ca57a2c0b1424523e7ee8450335053923ab629e47`,
17,042,819 bytes) ships next to the converter); superseded 0.38 (build `native-20261109T211151Z-03e89050` cut from `main`
@ `da1e68f`, 2026-11-09): the --force forced start for the documented
SteamOS state-lock dead end (the user-requested `--force` startup
parameter (accepted by the frozen trainer EXE (`launcher.py`), the
source CLI `run` + `master` commands (`__main__.py`) and the frozen
`CT2Trainer-Master.exe` (`tools/native_master.py`)) skips the state-lock
safety prompts: a recoverable stale state (dead state-lock owner) or
unfinished receipts are archived through the tested
`perform_stale_recovery` path without a confirmation dialog; the fence
dead end (the plain `StateError` "A recovery transaction owns this
state", incl. the "state.lock already exists" probe fallback) triggers
the new bounded forced reclaim in the pure `state_force.py` layer
(`force_reclaim`): every recorded trainer-side owner is probed with the
tested process probe (one observation, one retry on a transient
"unknown"); a proven-alive trainer-side owner is still refused with its
named reason - the one hard data-safety boundary that stays even under
`--force`; every other case (proven-dead or unprovable owner)
quarantines the blocking artifacts (state.lock, recovery.lock,
session.json, state.json.tmp, oneshot.json.tmp, hook receipts /
global-pool, this trainer's shared claims) into a timestamped
`forced-recovery/<UTC stamp>-<trainer id>/` archive next to the state
folder with a full evidence document (`ct2trainer-forced-reclaim/v1`);
the saved `state.json` (the user's saved wishes) is always preserved, so
the saved toggles survive the forced reclaim; debug-log events
`state-force-recovered` / `-reclaimed` / `-refused` / `-failed`; on
Steam / SteamOS: `--force` in the launch options so the Proton-wrapped
trainer starts without any dialog); +27 tests, full main suite 4,760 OK
/ 30 expected skips, catalog zero delta `blocked-catalog-038-force`;
in-build suite 4,760 OK / 30 expected skips, `ce_inputs: []`,
`runtime_unverified` deliberately kept per gate; source ZIP
`CT2Trainer-0.38-source.zip` sha256
`e2b466adc7abfb191bbd2b50f8304739a1e82cbf487099d4ecd6fd77cc3f3d0c`
(14,521,497 bytes) - carries the --force forced start (`state_force.py`
pure layer + the `force_reclaim` quarantine archive,
`tests/test_native_state_force.py` +
`tests/test_native_master_force.py`) and the reviewable
`master_trainer/UI.md` - and portable ZIP
`CT2Trainer-0.38-windows-portable.zip` sha256
`df5ccfa373c8f5deb6be85f36e75941a1c0b3a9f13afae23c03f1644f9290fc4`
(49,781,948 bytes; the frozen `CT2Trainer-Master.exe` (sha256
`5d2cc5544eb6a29f1c3283f05e809e392d0038a1f59456c9d52f0356e519231d`,
17,026,316 bytes) ships next to the converter); superseded 0.37 (build
`native-20261109T154005Z-4ad8e339` cut from `main` @ `27dbf0d`,
2026-11-09): the Master Trainer per-table process
binding persistence (MT-28: the explicit process choice is
remembered per table - `table-attach.json` schema 1 under the
state home, keyed by the table content sha256 - the same
identity as the MT-24 analysis and the MT-27 notes documents,
so a remembered choice survives a rename and follows a
content-identical file to another root; a live remembered choice
outranks the documented smallest-PID rule in auto mode; in ask
mode the picker still opens (the documented contract) with the
remembered row preselected so the one-click attach is the
remembered target; a stale or foreign PID falls back to the
ordinary attach decision; every picker origin persists the
choice (auto-load, explicit load, table choice, re-attach after
a detach - the attach origin addresses the loaded table through
the sidecar sha); a table without a content sha cannot carry a
binding (the documented MT-27 identity rule); the MT-22
table-details window shows the "Remembered process" row; zero
load-path effect - the MT-9 gate re-checks the table
independently at load time); +68 tests, full main suite 4,733 OK
/ 30 expected skips, catalog zero delta
`blocked-catalog-037-attach`; in-build suite 4,733 OK / 30
expected skips, `ce_inputs: []`, `runtime_unverified`
deliberately kept per gate; source ZIP
`CT2Trainer-0.37-source.zip` sha256
`a49bdd7d738de9551a1d971430ed9f7b0a212ec0d4a2afd8667e1f87ec61d301`
(14,506,715 bytes) - carries the MT-28 per-table process
binding persistence (`table_attach.py` pure layer +
`table-attach.json` schema 1,
`tests/test_native_master_attach.py` +
`tests/test_native_master_ui_mt28.py`) and the reviewable
`master_trainer/UI.md` - and portable ZIP
`CT2Trainer-0.37-windows-portable.zip` sha256
`5cdb23b24c0757cb047ddd72ae673614fc6bccee960747079849fe325785c3ce`
(49,762,223 bytes; the frozen `CT2Trainer-Master.exe` (sha256
`c2a1a6948fa28248d36a6defa5a116867620261e55bdcfe1e144cd301060a9de`,
17,017,090 bytes) ships next to the converter); superseded 0.36 (build
`native-20261109T114726Z-15c3d9ab` cut from `main` @ `d071884`,
2026-11-09): the Master Trainer multi-column
trainer grid (MT-21: the trainer row grid can run in up to three
side-by-side columns - the requested column count (1 / 2 / 3,
default 1) persists in the master state (master-settings.json
schema 8 -> 9, grid_columns) and is handed to the trainer window
on table load; the trainer header gains the "Columns: N" cycle
button (master only - the standalone trainer header stays
byte-identical and always renders the single column); a narrow
window renders fewer columns than requested (two columns need
652 px, three need 984 px, a column never falls below the 320 px
floor); a section with its children never splits across columns;
the pure grid layer in ui_rows.py (build_grid / effective_columns
/ column_layout / row_units / flow_units, columns == 1
byte-stable against build_rows); per-column pagination and
per-column hit-testing; zero load-path effect - the MT-9 gate
re-checks the table independently at load time); +55 tests, full
main suite 4,665 OK / 30 expected skips, catalog zero delta
`blocked-catalog-036-grid`; in-build suite 4,665 OK / 30 expected
skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per
gate; source ZIP `CT2Trainer-0.36-source.zip` sha256
`79464f02cd71492763656ca0ff3283a240c3579b9f52df3bcc18857dabb3d1be`
(14,490,858 bytes) - carries the MT-21 multi-column trainer grid
(`ui_rows.py` grid pure layer + `master_state.py` schema 9,
`tests/test_native_ui_grid.py` +
`tests/test_native_master_ui_mt21.py`) and the reviewable
`master_trainer/UI.md` - and portable ZIP
`CT2Trainer-0.36-windows-portable.zip` sha256
`089fc92b0c5758ba758fdc88bb92e11d8e3b3e36c28d04231f27b3eeaecceac0`
(49,751,886 bytes; the frozen `CT2Trainer-Master.exe` (sha256
`07ebef319b55d686c4f76cdb6f07440a2b4934fc8943f9f72b402d62c4c49fe8`,
17,006,463 bytes) ships next to the converter); superseded 0.35 (build
`native-20261109T054146Z-c5f18494` cut from `main` @ `65d8fbe`,
2026-11-09): the Master Trainer per-table notes / tags
(MT-27: the waiting view gains the Note column - the persisted
per-table organization metadata (note text truncated, tags in
brackets, empty while no note exists); the row context menu
"Edit note..." between load and pin - the small Toplevel with the
note (multi-line, bounded at 500 characters) and a
comma-separated tag entry (bounded at 8 tags x 40 characters); a
named refusal at save time is shown in the dialog's own label -
the dialog stays open, the persisted document is untouched; a
table without a content sha (unreadable / never scanned) is
refused in the status line; the notes persist in
`table-notes.json` schema 1, under the state home, keyed by the
table content sha256 - the same identity as the MT-24 analysis
document, so a note survives a rename and follows a
content-identical file across roots; LRU-bounded to 1024 entries;
no master-state schema bump - the MT-24 sidecar precedent; the
waiting-view filter also matches the note text and tags, and the
MT-22 details window shows the note / tag rows; zero load-path
effect - the MT-9 gate re-checks the table independently at load
time); +67 tests, full main suite 4,610 OK / 30 expected skips,
catalog zero delta `blocked-catalog-035-notes`; in-build suite
4,610 OK / 30 expected skips, `ce_inputs: []`,
`runtime_unverified` deliberately kept per gate; source ZIP
`CT2Trainer-0.35-source.zip` sha256
`575ee8ad6f0864bd8ff39f3ae547bb629d5c128938cff792e9c4fb7362fbcdac`
(14,474,384 bytes) - carries the MT-27 per-table notes / tags
(`table_notes.py` pure layer + `table-notes.json` schema 1,
`tests/test_native_master_notes.py`) and the reviewable
`master_trainer/UI.md` - and portable ZIP
`CT2Trainer-0.35-windows-portable.zip` sha256
`488d7453ca0433f843c1e46a2241142347aa2ee41390ed334d6068ed30e42d34`
(49,737,899 bytes; the frozen `CT2Trainer-Master.exe` (sha256
`0c53908c267746cabd74e1ef091daa35d31eb94c4d0accc6401085d7e8c59ccc`,
16,999,124 bytes) ships next to the converter); superseded 0.34
(build `native-20261109T024143Z-a5457911` cut from `main` @ `dc00343`,
2026-11-09): the Master Trainer multi-root table
index (MT-26: the Master indexes several table folders at once -
every root keeps the same (size, mtime_ns) + sha256 short-circuit
reconcile contract; the merged surface distinguishes tables by the
absolute table key (index root + relative path) with the
documented relative-path fallback; the "Folders..." header button
opens the folder manager (add / remove / set primary, the primary
marked with a star); the waiting view gains the Folder column; the
persisted folder list, master-state schema 7 -> 8, table_folders,
primary first, cap 8; the tables index document schema 1 -> 2 - one
checksum-bound root block per indexed folder; run_master
multi-root folder resolution: an explicit folder argument wins as
the primary root with the stored folders indexed behind it
(casefold-deduped), a parameterless start keeps the stored list (a
missing stored folder stays visible as a scan problem), only a
genuinely first start shows the picker (cancel exits 0), an
explicit missing folder is the documented exit-2 refusal; zero
load-path effect - the MT-9 gate re-checks the table under its
index root independently at load time); +44 tests, full main suite
4,543 OK / 30 expected skips, catalog zero delta
`blocked-catalog-034-mt26`; in-build suite 4,543 OK / 30 expected
skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per
gate; source ZIP `CT2Trainer-0.34-source.zip` sha256
`0d0a0849a90171f64eaf5b55ec06ec1d9117d02d5330895dcb4279e26f73b0f5`
(14,455,170 bytes) - carries the MT-26 multi-root table index
(`table_index.py` `RootIndexSet` + schema-2 index set,
`master_state.py` schema 8,
`tests/test_native_master_ui_mt26.py`) and the reviewable
`master_trainer/UI.md` - and portable ZIP
`CT2Trainer-0.34-windows-portable.zip` sha256
`ade1ecc520ddbeaf6886e1b195fc6e2886a5f9cbeaa64b15f9ac5679420f5054`
(49,719,386 bytes; the frozen `CT2Trainer-Master.exe` (sha256
`606ea2287eb9f787308d862c18209076ee42e4f7a4ae88fcb93bf8f22edcb6f6`,
16,983,514 bytes) ships next to the converter); superseded 0.33
(build `native-20261108T200230Z-b0167049` cut from `main` @
`6e71739`, 2026-11-08). The 0.16
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

**CT2Trainer (status 2026-11-27, 0.52.5 released - build
`native-20261127T153032Z-826c36d0` cut from `main` @ `1595bae`,
2026-11-27, in-build suite 5,271 OK / 36 expected skips, `ce_inputs:
[]` - the Great Circle crash case trainer-side regression fix +
widened 0.33 baseline proof (patch; the widened deterministic
replay at 0.33 (`main` @ `6e71739`) is byte-identical vs 0.41 AND
vs current main in activation and steady-state target traffic -
22 scans / 34 writes / 6 allocations, identical patterns / counts
/ addresses / order, clean close, normalized deep diff TOTAL
DIFFERENCES: 0 in both comparisons, plan canonical sha 0.33 ==
0.41, the only plan delta vs main the 15 empty
`unowned_cleanup_dropped: []` fields from the 0.42
cleanup-parity change - isolating the 0.39 bounded transient-read
retry as the ONLY new target-touching behavior in the 0.33 →
0.52.3 window, which until now also applied to the bounded rearm
module scans, the 122 MB GC module read in ~1 MiB chunks; the
fix restores pre-0.39 abort-on-first-transient-read for the scan
paths only: keyword-only `retry_transient` on `read()` /
`_read_exact()` with default `True` keeping the 0.39 retry for
one-shot reads, `scan_module` / `scan_matches` reading every
chunk with `retry_transient=False` so a transient
ReadProcessMemory failure (299/119/1116/24) aborts the scan on
the first attempt without extra kernel reads or backoff sleep
under the memory lock and records the abort context in
`last_scan_diagnostics`, a completed scan records `bytes_scanned`
and replaces the stale abort context via the object-identity
guard); + the widened scan forensics in `engine.py`
(`rearm-scan-start` bracketing every rearm attempt,
`scan_transient_abort` / `bytes_scanned` on the rearm-attempt
end event, the named `scan-transient-abort` event on the
byte-patch `_operations` + program-preflight scan paths;
evidence-side only, no-op with the plan `debug_log` off, on in
field builds); proof git-tracked at
`documentation/evidence/gc-0525-baseline-033/`; +16 tests (new
`tests/test_native_scan_transient_abort.py` +
`tests/test_native_scan_forensics.py`, fixture re-pins in six
test files); full main suite 5,271 OK / 36 expected skips;
catalog unchanged at the `blocked-catalog-luacall-binding` /
`blocked-catalog-0523-great-circle` baseline (117,809 total /
117,616 supported / 12,974 headings / 104,467 actionable /
193 blocked - the scan-abort change touches no table-parsing
path, no remeasure); the mechanical doubt stays on record
(kernel-mediated ReadProcessMemory cannot crash the target; the
read-attempt delta is argued statically) - field confirmation
requested: WER dumps + a 0.31-vs-0.52.5 A/B run with the rearm
scan forensics on; see the 0.52.5 Great Circle case section +
0.52.5 release build record in `documentation/native-progress.md`;
superseded 0.52.4 (build `native-20261126T125152Z-c8a75b03` cut
from `main` @ `7585cc8`, 2026-11-26, in-build suite 5,255 OK /
36 expected skips, `ce_inputs: []` - the Great Circle crash
re-analysis + forensics release
(patch; the user-overruled 0.52.3 "game-side" crash attribution
re-analyzed at byte level: the 0.41 -> 0.52.3 window is
byte-identical in activation AND steady-state tick-path target
traffic - the replay deep-diff reports TOTAL DIFFERENCES: 0 across
15 categories, the steady-state tick path (`poll` /
`_check_patches` / `read_value` / `_run_rearm`) differs only in
the 0.43 read-side transient-read-skip + the streak reset on
attach, the `ui.py` tick loop is unchanged in cadence or target
traffic and the GC plan declares no per-record hotkeys (MT-34
path inert); the field logs show the trainer read-only-idle in
both crash windows, the trailing Win32 299 verify-skip ~260 ms
before `target-exited` a symptom; no statically provable
trainer-side crash mechanism in the window); the release ships
(a) the byte-level replay proof (git-tracked at
`documentation/evidence/gc-0524-replay/`, deliberately outside
the release allowlist), (b) the crash-forensics debug logging
(`entry-applied` event per installed program - patch addr /
before / after, allocations addr / size / content sha + bounded
content hex, module base / size - gated on the plan `debug_log`
flag, ON in the field builds; `_run_rearm` duration + game-module
scan range on every `rearm-attempt`) and (c) the documented field
test protocol (WER dump harvest, the 0.41 A/B control run, entry
bisection on 0.52.4, the cross-table Resonance check); +5 tests
(`tests/test_native_entry_forensics.py`), catalog unchanged at
the `blocked-catalog-luacall-binding` /
`blocked-catalog-0523-great-circle` baseline (117,809 total /
117,616 supported / 12,974 headings / 104,467 actionable /
193 blocked - the forensics touch no table-parsing path); the
actual crash fix awaits the requested field data; see the Great
Circle crash case + 0.52.4 release build record in
`documentation/native-progress.md`; superseded 0.52.3 (build
`native-20261126T030208Z-a082e323` cut from `main` @ `421d7c7`,
2026-11-26, in-build suite 5,250 OK / 36 expected skips,
`ce_inputs: []` - the Great Circle field fix release (D1:
direction-aware prefix-cut close validation -
`validate_entry_prefix_cut` gains keyword-only
`expect_live_original`, so at disable the live prefix is
compared against the replacement instead of the captured
original, fixing the deterministic "Entry patch bytes changed
before validation" close refusal on prefix-cut entries; D2:
bounded startup re-assessment - one re-assessment after a
1.5 s wait when a transient state-directory inventory change
aborts the process proof, fixing the misleading "not proven dead
in both observations (absent)" refusal on a stable state); +7
tests, catalog zero delta `blocked-catalog-0523-great-circle`;
both fixes stand as proven real defects but do not address the
crash; superseded 0.52.2 (build
`native-20261124T033652Z-1da5b40e` cut from `main` @ `cbbd386`,
2026-11-24, in-build suite 5,235 OK / 36 expected skips,
`ce_inputs: []` - the RT-7 in-build suite determinism release
(the per-test leaked-Tk-interpreter elimination; full-suite
per-test leak scan START-ROOTS 0 / FINAL-ROOTS 0, zero
LEAK-DELTA vs the 2026-11-23 v3 baseline) + the six-family
fixture rebuild + re-pin for the frozen gate re-runs at that cut
(the probe `TARGET_SHA256` pins moved hash-only, no compiler
drift); the frozen re-runs of all eleven owned gates ran at that
cut on the 0.52.2 template stub (sha256
`20c17ee135c9bfb388612ade31e1cad5ee032768044f29d4099344017c34ce25`),
every report passed with `frozen_runtime: true` (14/14 string per
architecture, 6/6 x86 debug-hook, 7/7 hook, 4/4 Lua-record, 14/14
global per architecture, 8/8 scan per architecture, 14/14
code-patch per architecture; the first frozen x86 code-patch run
of the roadmap ran from an elevated parent per the documented VM
launch-block heuristic with the user-approved UAC consent);
post-0.52.1 (2026-11-16 + 2026-11-20) the owned code-patch
fixture gate (the 9th Windows function gate, RT-6 fixture-owned,
house pattern per `global_probe.py`) verified in the source
runtime - x64 passed 14/14 on 2026-11-16 (report
`ct2trainer-owned-codepatch/v1`, `source_runtime: true`,
`ce_implementation_inputs: []`, `owned_markers_absent: true`;
full RT-5 item B `code_patch` lifecycle against a live owned
target incl. the recorded live-close fence), the x86
source-runtime run passed 14/14 on 2026-11-20 (report stamp
`20261119T235133Z` UTC; the same 14 named checks, against the
pinned x86 target sha256
`288855467feab361c2d27a64a4ff68bb73687923d8e3984003a3c7fe77ae6a85`
(PE machine 0x14C / pointer width 32), canonical plan
fingerprint
`c67846921cafeedb36387e465efa88fdaa95e80c7526bc485df817b8d6a28061`,
live x86 RVAs byte-exact vs the static measurement, the
target's own protocol executed the patched probe entry
0x46474849 through the verified hook coordinator, recorded
live-close fence holds; machine note: the x86 target launches
only from an elevated parent - non-elevated `CreateProcess`
fails with Win32 740, a name + architecture launch-block
heuristic (any x86 executable with a "patch"-like name was
refused regardless of content, path, parent or caller
context, while x64 binaries with the same names, x86 with
clean names and "dispatch" launched fine); the SAC
first-launch hypothesis is refuted - SAC registry state off /
never enabled, no SAC operations log, no block events, prompt
approval ineffective - and AppLocker / WDAC / SRP are absent
or empty, no MOTW, no elevation manifest, no third-party
AV/EDR; Windows Defender behavior monitoring is the active
enforcer on this VM, a Defender exclusion for the fixture
process + the run paths was added and read back as registered
during the clearance, and the elevated source-runtime run is
the recorded evidence), +24 tests, full main suite 5,227 OK /
36 expected skips, catalog unchanged at the
`blocked-catalog-luacall-binding` baseline; the frozen re-runs
(the generated trainers, `frozen_runtime: true`) of both
architectures ran at the 0.52.2 release cut (2026-11-24, template
stub sha256
`20c17ee135c9bfb388612ade31e1cad5ee032768044f29d4099344017c34ce25`):
both reports status `passed` with 14/14 checks and plan identity
identical to the source runtime (the x86 run from an elevated
parent per the documented heuristic with the user-approved UAC
consent; see the 0.52.2 release build record);
post-0.52.1 (2026-11-21) the ROG Ally field observation (the
0.52.1 trainer is refused by Smart App Control before any code
executes - unsigned binary by hash, no per-app allow, one-way
off switch; the requested UAC elevation cannot clear the block
- the refusal happens before process start and the trainer
needs no elevation for a same-user-session attach) + the
mechanical end-to-end verification of the 0.47 code-signing
pipeline on this machine with a self-signed test certificate
(mechanism proof only - self-signed does not clear SAC, per the
0.47 record): the production environment seam signed both
0.52.1 artifacts with RFC3161 timestamping, the pure
certificate-table re-proof passed (the PyInstaller onefile
overlay layout - certificate table appended after the overlay,
security directory RVA carrying its file offset, type 0x0002
PKCS#7 - is now accepted with the same well-formed proof), the
embedded plan is identical in canonical sha256 behind the
appended certificate table, and the signed master boots; two
production defects found and fixed (fail-closed, +5 tests: the
resolved signtool discovery path was overridden by the
discovery config's `None` in the argv merge - raw TypeError on
the PFX-only contract; the pure re-proof refused every real
Authenticode signature - required type 0x0001 instead of the
Authenticode 0x0002 and required the security directory RVA to
map into a section); full main suite 5,232 OK / 36 expected
skips, catalog unchanged at the
`blocked-catalog-luacall-binding` baseline; the durable SAC fix
stays a user-supplied trusted-CA PFX through the documented
`CT2TRAINER_SIGN_PFX` environment contract (fail-closed: a
configured signing failure never ships an unsigned binary) -
the signed release cut activates once the certificate is in
hand;
superseded 0.52.1, build `native-20261115T181026Z-00f5dfe8` cut
from `main` @ `dc138e0`, 2026-11-15, in-build suite 5,203 OK / 36
expected skips, `ce_inputs: []; superseded 0.52, build
`native-20261115T070952Z-14405931` cut
from `main` @ `26e6ebc`, 2026-11-15, in-build suite 5,197 OK / 36
expected skips, `ce_inputs:
[]`; superseded 0.51, build `native-20261115T023110Z-4ed2835e` cut
from `main` @ `35542f4`, 2026-11-15, in-build suite 5,184 OK / 36
expected skips, `ce_inputs: []`; superseded 0.50, build `native-20261114T223759Z-086989d6` cut
from `main` @ `4f747ce`, 2026-11-14, in-build suite 5,171 OK / 36
expected skips, `ce_inputs: []`; superseded 0.49, build `native-20261114T184922Z-4b721a9e` cut
from `main` @ `20c63c1`, 2026-11-14, in-build suite 5,155 OK / 36
expected skips, `ce_inputs: []`; superseded 0.48, build `native-20261114T133842Z-8ee6999f` cut
from `main` @ `5d467dc`, 2026-11-14, in-build suite 5,127 OK / 36
expected skips, `ce_inputs: []`; superseded 0.47, build `native-20261114T011046Z-ee5cecee` cut
from `main` @ `6e1940e`, 2026-11-14, in-build suite 5,108 OK / 36
expected skips, `ce_inputs: []`; superseded 0.46, build `native-20261113T185658Z-e543af1a` cut
from `main` @ `b348184`, 2026-11-13, in-build suite 5,071 OK / 36
expected skips, `ce_inputs: []`; superseded 0.45, build
`native-20261113T144426Z-572d5b30` cut from `main` @ `58d6c8f`,
2026-11-13, in-build suite 5,062 OK / 36 expected skips, `ce_inputs:
[]`; superseded 0.44, build
`native-20261112T233337Z-1dc678c6` cut from `main` @ `ab11893`,
2026-11-13, in-build suite 5,049 OK / 36 expected skips, `ce_inputs:
[]`; superseded 0.43, build
`native-20261111T184600Z-3bf9d8aa` cut from `main` @ `0df2607`,
2026-11-11, in-build suite 5,011 OK / 36 expected skips, `ce_inputs:
[]`; superseded 0.42, build
`native-20261111T044023Z-04112d15` cut from `main` @ `377f760`,
2026-11-11, in-build suite 4,926 OK / 35 expected skips, `ce_inputs:
[]`; superseded 0.41, build
`native-20261110T210856Z-5811040c` cut from `main` @ `c724a7e`,
2026-11-10, in-build suite 4,917 OK / 35 expected skips, `ce_inputs:
[]`; superseded 0.40, build
`native-20261110T093203Z-82c49872` cut from `main` @ `e611e9e`,
2026-11-10, in-build suite 4,879 OK / 35 expected skips, `ce_inputs:
[]`; superseded 0.39, build
`native-20261110T051241Z-57bf7d47` cut from `main` @ `17a22f7`,
2026-11-10, in-build suite 4,833 OK / 30 expected skips, `ce_inputs:
[]`; superseded 0.38, build
`native-20261109T211151Z-03e89050` cut from `main` @ `da1e68f`,
2026-11-09, in-build suite 4,760 OK / 30 expected skips, `ce_inputs:
[]`; superseded 0.37, build
`native-20261109T154005Z-4ad8e339` cut from `main` @ `27dbf0d`,
2026-11-09, in-build suite 4,733 OK / 30 expected skips,
`ce_inputs: []`; superseded 0.36, build
`native-20261109T114726Z-15c3d9ab` cut from `main` @ `d071884`,
2026-11-09, in-build suite 4,665 OK / 30 expected skips,
`ce_inputs: []`; superseded 0.35, build
`native-20261109T054146Z-c5f18494` cut from `main` @ `65d8fbe`,
2026-11-09, in-build suite 4,610 OK / 30 expected skips,
`ce_inputs: []`; superseded 0.34, build
`native-20261109T024143Z-a5457911` cut from `main` @ `dc00343`,
2026-11-09, in-build suite 4,543 OK / 30 expected skips,
`ce_inputs: []`; superseded 0.33, build
`native-20261108T200230Z-b0167049` cut from `main` @ `6e71739`,
2026-11-08, in-build suite 4,499 OK / 30 expected skips,
`ce_inputs: []`) - 0.40 the Master Trainer process
identification in picker + details (MT-31) + the bounded
zero-transfer transient-write retry in `memory.py` (the
optional identification fields `path` / `creation_time` /
`pointer_size` on `ProcessSnapshotEntry`, all default `None`
- fail-closed, the row keeps the byte-stable name + PID form,
the `pid` / `name` decision fields are never touched; the
bounded per-candidate enrichment only at picker + details
open - Windows `OpenProcess(PROCESS_QUERY_INFORMATION)` +
`QueryFullProcessImageNameW` + `GetProcessTimes` +
`IsWow64Process2`, procfs `exe` link target + `stat` field 22
+ `btime`; the picker rows and the table-details "Running
now" row render the proved facts, a refused fact never
renders; zero load-path effect, the MT-9 gate re-checks the
table independently at load time; the write-side symmetry of
the 0.39 transient-read retry: a `WriteProcessMemory` call
that FAILED with the transient set {299, 119, 1116, 24} and
transferred NOTHING is retried in `memory._write_checked`
with the bounded exponential backoff - exactly 4 attempts,
backoff 0.05 -> 0.25 s; a partial transfer or any
non-transient code is never retried, the original error is
raised unchanged after the budget - completing the read /
write pair); +46 tests, full main suite 4,879 OK / 35
expected skips, catalog zero delta
`blocked-catalog-040-process-id`; in-build suite 4,879 OK /
35 expected skips, `ce_inputs: []`, `runtime_unverified`
deliberately kept per gate; source ZIP
`CT2Trainer-0.40-source.zip` sha256
`46ad5dd9f9adc872e320dd4aec2362e007020ae879bba0cc8fe0621e44c34c40`
(14,569,029 bytes) - carries the MT-31 process
identification (`process_watch.py` enrichment layer +
`tests/test_native_master_ui_mt31.py`) and the bounded
transient-write retry
(`tests/test_native_memory_write_retry.py`) and the
reviewable `master_trainer/UI.md` - and portable ZIP
`CT2Trainer-0.40-windows-portable.zip` sha256
`5075586c7b0f3251749c8e3e60ec0db7fea251db39190b59b63273a4e9b10bd6`
(49,809,535 bytes; the frozen `CT2Trainer-Master.exe` (sha256
`52f6da1cebfc44a0dc791d4b5758112342b5a1d42c9fc9656901a16d1a5eb03f`,
17,048,910 bytes) ships next to the converter); superseded 0.39 released (build
`native-20261110T051241Z-57bf7d47` cut from `main` @ `17a22f7`,
2026-11-10) - 0.39 the Master Trainer per-table auto-load
policy (MT-29) + state folder / debug log quick access (MT-30) +
the bounded transient-read retry in `memory.py` (the per-table
auto-load policy `table-autoload.json` schema 1 under the state
home, content-sha keyed - the same identity as the MT-24/27/28
sidecars; only the non-default manual-only persists, absence =
documented auto; a manual-only table is never auto-loaded - no
request, no picker, a stable named waiting detail, an open
choice dropped back to waiting; the explicit MT-10 load path is
never affected; the orchestrator re-evaluates the policy on
every tick; the row context menu toggle + the MT-22 details row
+ the filter matches the persisted policy text; the two
master-only header buttons "State folder..." / "Debug log..."
through the pure `state_access.py` layer with named
`StateAccessRefusal` codes - every refusal in the status line,
never a dialog, never a crash; the field-observed Win32 299
transient read failure now retried in `memory._read_exact`:
transient set {299, 119, 1116, 24}, 4 attempts, 0.05 -> 0.25 s
backoff, partial never retried, original error after the budget
- closing the documented open issue of the 0.38 ledger); +73
tests, full main suite 4,833 OK / 30 expected skips, catalog
zero delta `blocked-catalog-039-autoload`; in-build suite 4,833
OK / 30 expected skips, `ce_inputs: []`, `runtime_unverified`
deliberately kept per gate; source ZIP
`CT2Trainer-0.39-source.zip` sha256
`14163e7475477c177be339d06fd5ba7b9a7016667405669b084faed25035a923`
(14,549,960 bytes) - carries the MT-29 auto-load policy
(`table_autoload.py` pure layer + `table-autoload.json`
schema 1, `tests/test_native_master_autoload.py` +
`tests/test_native_master_ui_mt29.py`), the MT-30 state folder
/ debug log quick access (`state_access.py` pure layer,
`tests/test_native_master_ui_mt30.py`) and the bounded
transient-read retry
(`tests/test_native_memory_read_retry.py`) and the reviewable
`master_trainer/UI.md` - and portable ZIP
`CT2Trainer-0.39-windows-portable.zip` sha256
`7d5d7903f1be5df0eac0f1067d5c2ca596321a41ea37381e033e5deb175ec8b6`
(49,800,752 bytes; the frozen `CT2Trainer-Master.exe` (sha256
`e0db5b2e2f41ec816089486ca57a2c0b1424523e7ee8450335053923ab629e47`,
17,042,819 bytes) ships next to the converter); superseded 0.38 released (build
`native-20261109T211151Z-03e89050` cut from `main` @ `da1e68f`,
2026-11-09) - 0.38 the --force forced start for the documented SteamOS state-lock
dead end (the user-requested `--force` startup parameter (accepted by
the frozen trainer EXE (`launcher.py`), the source CLI `run` + `master`
commands (`__main__.py`) and the frozen `CT2Trainer-Master.exe`
(`tools/native_master.py`)) skips the state-lock safety prompts: a
recoverable stale state (dead state-lock owner) or unfinished receipts
are archived through the tested `perform_stale_recovery` path without a
confirmation dialog; the fence dead end (the plain `StateError` "A
recovery transaction owns this state", incl. the "state.lock already
exists" probe fallback) triggers the new bounded forced reclaim in the
pure `state_force.py` layer (`force_reclaim`): every recorded
trainer-side owner is probed with the tested process probe (one
observation, one retry on a transient "unknown"); a proven-alive
trainer-side owner is still refused with its named reason - the one hard
data-safety boundary that stays even under `--force`; every other case
(proven-dead or unprovable owner) quarantines the blocking artifacts
(state.lock, recovery.lock, session.json, state.json.tmp,
oneshot.json.tmp, hook receipts / global-pool, this trainer's shared
claims) into a timestamped `forced-recovery/<UTC stamp>-<trainer id>/`
archive next to the state folder with a full evidence document
(`ct2trainer-forced-reclaim/v1`); the saved `state.json` (the user's
saved wishes) is always preserved, so the saved toggles survive the
forced reclaim; debug-log events `state-force-recovered` / `-reclaimed`
/ `-refused` / `-failed`; on Steam / SteamOS: `--force` in the launch
options so the Proton-wrapped trainer starts without any dialog); +27
tests, full main suite 4,760 OK / 30 expected skips; catalog zero delta
`blocked-catalog-038-force`), superseded 0.37 released (build
`native-20261109T154005Z-4ad8e339` cut from `main` @ `27dbf0d`,
2026-11-09) - 0.37 Master Trainer per-table process
binding persistence (MT-28: the explicit process choice is
remembered per table - `table-attach.json` schema 1 under the
state home, keyed by the table content sha256 - the same
identity as the MT-24 analysis and the MT-27 notes documents,
so a remembered choice survives a rename and follows a
content-identical file to another root; a live remembered choice
outranks the documented smallest-PID rule in auto mode; in ask
mode the picker still opens (the documented contract) with the
remembered row preselected so the one-click attach is the
remembered target; a stale or foreign PID falls back to the
ordinary attach decision; every picker origin persists the
choice (auto-load, explicit load, table choice, re-attach after
a detach - the attach origin addresses the loaded table through
the sidecar sha); a table without a content sha cannot carry a
binding (the documented MT-27 identity rule); the MT-22
table-details window shows the "Remembered process" row; zero
load-path effect - the MT-9 gate re-checks the table
independently at load time); +68 tests, full
main suite 4,733 OK / 30 expected skips; catalog zero delta
`blocked-catalog-037-attach`), superseded 0.36 released (build
`native-20261109T114726Z-15c3d9ab` cut from `main` @ `d071884`,
2026-11-09) - 0.36 Master Trainer multi-column trainer grid
(MT-21: the trainer row grid can run in up to three
side-by-side columns - the requested column count (1 / 2 / 3,
default 1) persists in the master state (master-settings.json
schema 8 -> 9, grid_columns) and is handed to the trainer window
on table load; the trainer header gains the "Columns: N" cycle
button (master only - the standalone trainer header stays
byte-identical and always renders the single column); a narrow
window renders fewer columns than requested (two columns need
652 px, three need 984 px, a column never falls below the 320 px
floor); a section with its children never splits across columns;
the pure grid layer in ui_rows.py (build_grid / effective_columns
/ column_layout / row_units / flow_units, columns == 1
byte-stable against build_rows); per-column pagination and
per-column hit-testing; zero load-path effect - the MT-9 gate
re-checks the table independently at load time); +55 tests, full
main suite 4,665 OK / 30 expected skips; catalog zero delta
`blocked-catalog-036-grid`), superseded 0.35 released (build
`native-20261109T054146Z-c5f18494` cut from `main` @ `65d8fbe`,
2026-11-09) - 0.35 Master Trainer per-table notes / tags
(MT-27: the waiting view gains the Note column - the persisted
per-table organization metadata (note text truncated, tags in
brackets, empty while no note exists); the row context menu
"Edit note..." between load and pin - the small Toplevel with the
note (multi-line, bounded at 500 characters) and a
comma-separated tag entry (bounded at 8 tags x 40 characters); a
named refusal at save time is shown in the dialog's own label -
the dialog stays open, the persisted document is untouched; a
table without a content sha (unreadable / never scanned) is
refused in the status line; the notes persist in
`table-notes.json` schema 1, under the state home, keyed by the
table content sha256 - the same identity as the MT-24 analysis
document, so a note survives a rename and follows a
content-identical file across roots; LRU-bounded to 1024 entries;
no master-state schema bump - the MT-24 sidecar precedent; the
waiting-view filter also matches the note text and tags, and the
MT-22 details window shows the note / tag rows; zero load-path
effect - the MT-9 gate re-checks the table independently at load
time); +67 tests, full main suite 4,610 OK / 30 expected skips;
catalog zero delta `blocked-catalog-035-notes`), superseded 0.34
released (build
`native-20261109T024143Z-a5457911` cut from `main` @ `dc00343`,
2026-11-09) - 0.34 Master Trainer multi-root table index
(MT-26: the Master indexes several table folders at once - every
root keeps the same (size, mtime_ns) + sha256 short-circuit
reconcile contract; the merged surface distinguishes tables by the
absolute table key (index root + relative path) with the
documented relative-path fallback; the "Folders..." header button
opens the folder manager (add / remove / set primary, the primary
marked with a star, every action re-scans the indexed roots, saves
the index and restarts the auto-rescan clock); the waiting view
gains the Folder column; the persisted folder list, master-state
schema 7 -> 8, table_folders, primary first, cap 8; the tables
index document schema 1 -> 2 - one checksum-bound root block per
indexed folder; run_master multi-root folder resolution: an
explicit folder argument wins as the primary root with the stored
folders indexed behind it (casefold-deduped), a parameterless start
keeps the stored list (a missing stored folder stays visible as a
scan problem), only a genuinely first start shows the picker (cancel
exits 0), an explicit missing folder is the documented exit-2
refusal; zero load-path effect - the MT-9 gate re-checks the table
under its index root independently at load time); +44 tests, full
main suite 4,543 OK / 30 expected skips; catalog zero delta
`blocked-catalog-034-mt26`), superseded 0.33 released (build
`native-20261108T200230Z-b0167049` cut from `main` @ `6e71739`,
2026-11-08) - 0.33 Master Trainer table folder auto-rescan
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

**Latest verified build:** `native-20261126T125152Z-c8a75b03` (0.52.4,
cut from `main` @ `7585cc8`, 2026-11-26; in-build suite 5,255 OK / 36
expected skips, `ce_inputs: []`, `runtime_unverified` deliberately
kept per gate; source ZIP `CT2Trainer-0.52.4-source.zip` sha256
`6438cf8138af3fde79bc9123bf4a6a1031cbcde8d621a3c387506b45690960d4`
(14,819,531 bytes) - carries the Great Circle crash re-analysis
forensics (the `entry-applied` + rearm timing / scan-range events in
`engine.py` gated on the plan `debug_log` flag, the +5 tests, and the
git-tracked replay proof at `documentation/evidence/gc-0524-replay/`
deliberately outside the release allowlist) - and portable ZIP
`CT2Trainer-0.52.4-windows-portable.zip` sha256
`d083ba7ec55f8c124ab91a947dbc1dfb1e2c5a643f7a417dce9f2d5d76771420`
(49,952,762 bytes; the frozen `CT2Trainer-Master.exe` (sha256
`5181c50512465b7fe5dbf6ff039addab40dd8791678d2ce19d4c70c2f370e0ba`,
17,076,611 bytes) ships next to the converter)). 0.52.4 ships the
Great Circle crash re-analysis + forensics release (patch; the
user-overruled 0.52.3 "game-side" crash attribution re-analyzed at
byte level: the 0.41 -> 0.52.3 window is byte-identical in activation
AND steady-state tick-path target traffic - the replay deep-diff
reports TOTAL DIFFERENCES: 0 across 15 categories, the steady-state
tick path differs only in the 0.43 read-side transient-read-skip +
the streak reset on attach, the `ui.py` tick loop is unchanged in
cadence or target traffic and the GC plan declares no per-record
hotkeys (MT-34 path inert); no statically provable trainer-side crash
mechanism in the window; the release ships the byte-level replay
proof, the crash-forensics debug logging and the documented field
test protocol; the actual crash fix awaits the requested field data);
full main suite 5,255 OK / 36 expected skips; catalog unchanged at
the `blocked-catalog-luacall-binding` /
`blocked-catalog-0523-great-circle` baseline (117,809 total /
117,616 supported / 12,974 headings / 104,467 actionable / 193
blocked - the forensics touch no table-parsing path); the build ran
unsigned by default (`code_signing` not-configured - no certificate
on this machine, the signed path activates with a user-supplied
trusted-CA PFX; see the Great Circle crash case section and the
0.52.4 release build record in `documentation/native-progress.md`).
Superseded 0.52.3 (build
`native-20261126T030208Z-a082e323` cut from `main` @ `421d7c7`,
2026-11-26; in-build suite 5,250 OK / 36 expected skips,
`ce_inputs: []`; source ZIP `CT2Trainer-0.52.3-source.zip` sha256
`d9643b3c847b6b109ddb2f924df9200e80594082775be5b3092fa2351815a7c5`
(14,814,477 bytes), portable ZIP
`CT2Trainer-0.52.3-windows-portable.zip` sha256
`0ea6e59e38e62bbab4da87c348a957b41867c453809623f335bb98f6eb3e50d8`
(49,951,182 bytes; frozen `CT2Trainer-Master.exe` sha256
`74e1548a9d1ddb4581419fa423eade1a46680bc96e7da53cb6e3a82bebf6c49b`,
17,076,637 bytes) - the Great Circle field fix release: D1 the
direction-aware prefix-cut close validation (keyword-only
`expect_live_original` on `validate_entry_prefix_cut`) + D2 the
bounded startup re-assessment (one re-assessment after a 1.5 s wait
when a transient state-directory inventory change aborts the process
proof); both fixes stand as proven real defects but do not address
the crash, whose 0.52.3 "game-side" attribution is overruled by the
user and re-analyzed in 0.52.4; see the 0.52.3 release build record
in `documentation/native-progress.md`). Superseded 0.52.2 (build
`native-20261124T033652Z-1da5b40e` cut from `main` @ `cbbd386`,
2026-11-24; in-build suite 5,235 OK / 36 expected skips,
`ce_inputs: []`; source ZIP `CT2Trainer-0.52.2-source.zip` sha256
`e372b142f40a026826212ce7f40e30ef5906a0e590dc116e4680db86b167757a`
(14,809,824 bytes), portable ZIP
`CT2Trainer-0.52.2-windows-portable.zip` sha256
`219db7e96b84958158ce1a26dd817393b3f887897969e381b2cdefbfea369727`
(49,942,786 bytes; frozen `CT2Trainer-Master.exe` sha256
`74550f1f621a84518f906cffd7dd17c3c27581a6687f6a07b48984dc260fabcd`,
17,072,404 bytes)). 0.52.2 shipped the
RT-7 in-build suite determinism release (the per-test
leaked-Tk-interpreter elimination -
`TrainerWindow.release_search_trace()` in `close()` + explicit
root masters at all four `TrainerWindow` variable sites in
`ui.py`, the `_back_to_master` trace release in
`master_trainer/master_ui.py`, the extended
`tests/native_tk_teardown.py` backstop with the fail-closed
named refusal `tk-teardown-refusal:
tk-interpreter-release-failed`, the tray test mock-retention
fixes, +3 env-strip tests in
`tests/test_native_code_signing.py`; full-suite per-test leak
scan START-ROOTS 0 / FINAL-ROOTS 0, zero LEAK-DELTA vs the
2026-11-23 v3 baseline of 54 live roots) + the six-family
fixture rebuild + re-pin for the frozen gate re-runs at that
cut (the pinned fixture builds from 2026-11-15/16 had been
cleaned: all six families rebuilt from the unchanged sources
with the committed MSVC recipes into
`build\runs\native-{string,debughook,hook,global,scan,codepatch}-fixture-20261124T031403Z-76b8c44b`;
the probe `TARGET_SHA256` pins moved hash-only in
`string_probe.py` / `x86_probe.py` / `lua_record_probe.py` /
`global_probe.py` / `scan_probe.py` / `codepatch_probe.py` - the
pinned CTs, fixture sources and canonical plan fingerprints
unchanged, so no compiler drift; 10 of the 11 gates
re-verified in the source runtime against the rebuilt targets,
the codepatch x86 source run stopped at the documented
elevated-parent launch-block, Win32 740 - a launch refusal,
not a pin failure); the frozen re-runs of all eleven owned
gates re-ran at that cut on the 0.52.2 template stub (sha256
`20c17ee135c9bfb388612ade31e1cad5ee032768044f29d4099344017c34ce25`)
- all eleven frozen trainers passed with `frozen_runtime: true`
(14/14 string per architecture, 6/6 x86 debug-hook, 7/7 hook,
4/4 Lua-record, 14/14 global per architecture, 8/8 scan per
architecture, 14/14 code-patch per architecture; x86 / hook /
Lua-record / code-patch plan identity identical to the source
runtime; the scan x86 first attempt failed against a transient
orphan process and the retry on a clean process table passed;
the codepatch x86 run - the first frozen x86 code-patch run of
the roadmap - ran from an elevated parent per the documented
VM launch-block heuristic with the user-approved UAC consent;
trainers + reports under the git-ignored
`build\windows-fixture\frozen-check-20261124T040411Z\`); the
build ran unsigned by default (`code_signing` report: signed
false / not-configured) and the signed path activates with a
user-supplied trusted-CA PFX; catalog unchanged
(`blocked-catalog-luacall-binding`): 117,616 supported / 193
blocked (zero delta vs the 0.52.1 baseline - this cycle
touches no table-parsing path; the remaining 193 blocked rows
are the documented design / gate residuals of the 0.51
residual census, unchanged). Post-0.52.1 (2026-11-16, lane work - no release
cut): the owned code-patch fixture gate (the 9th Windows
function gate, RT-6 fixture-owned, house pattern per
`global_probe.py`) verified in the source runtime -
`tests/windows/codepatch_fixture/codepatch_target.c` + the
directory's committed recipe
`Invoke-CodePatchFixtureBuild.ps1` (MSVC `cl` 19.44.35229, run
`native-codepatch-fixture-20261116T032022Z-bdd3`,
`ct2trainer-owned-codepatch-build/v1` status `passed`,
`ce_inputs: []`; x64 EXE sha256
`3f217da553159221216db43c6c8e83481d5da2869edcdf68ca4f66980a9b891f`
147,456 B / x86 EXE sha256
`288855467feab361c2d27a64a4ff68bb73687923d8e3984003a3c7fe77ae6a85`),
the two pinned CTs in `tests/fixtures/codepatch/` (four
`<CodeEntry>` `code_patch` records each, 4 supported / 0
blocked; x64 plan file sha256
`cef82a71b2cf082a7764f0fd203a47634106468001f3a0eee5496e1dde9360c8`),
the new pure gate `src/ct2trainer/native/codepatch_probe.py`
(report schema `ct2trainer-owned-codepatch/v1`) + the
`--codepatch-fixture-target` / `--codepatch-fixture-report`
launcher pair in `launcher.py` (orphan flag or a mixed gate
refused before the plan is read): the x64 source-runtime run
passed 14/14 checks (`source_runtime: true`,
`frozen_runtime: false`, `ce_implementation_inputs: []`,
`owned_markers_absent: true`; plan + report under
`build\windows-fixture\codepatch-check-20261116T082357Z\`) -
the full RT-5 item B `code_patch` lifecycle against a live
owned target (data-page publish / capture / restore, overlap
refusal, target-changed refusal, already-active adoption,
executable-page routing through the verified hook coordinator
with the target's own protocol executing the patched entry,
the restore-mismatch engine block, the blocked engine's
action + second-controller refusals, target-exit
finalization of the blocked session through
`close-after-blocked` with both saved wishes persisted,
saved-ON replay of both routes on a fresh identity, replayed
disables, normal close after exit) + the dedicated recorded
live-close fence (a blocked live close on a third owned
target refuses with a `False` return and the exact
"code-patch-restore-mismatch" reason, touches nothing and
preserves `state.lock` / `session.json` / `state.json` / the
`enabled`-state executable journal across the target exit);
the x86 source-runtime run passed 14/14 on 2026-11-20
(report stamp `20261119T235133Z` UTC; plan + report under
`build\windows-fixture\codepatch-x86-check-20261119T235133Z\`,
git-ignored): x86 report `ct2trainer-owned-codepatch/v1`
status `passed`, `source_runtime: true`,
`frozen_runtime: false`, `ce_implementation_inputs: []`,
`owned_markers_absent: true` - the same 14 named checks as
the x64 run, all passed, against the pinned x86 target
(sha256
`288855467feab361c2d27a64a4ff68bb73687923d8e3984003a3c7fe77ae6a85`,
PE machine 0x14C / pointer width 32, canonical plan
fingerprint
`c67846921cafeedb36387e465efa88fdaa95e80c7526bc485df817b8d6a28061`,
plan file sha256
`b5439d46b1febeacb3acc6c2068bca98de60ff00b2ca2943c85551cd2fa412b9`):
the live module metadata confirms the static x86 RVA
measurement byte-exact (marker 0x16190, data_a 0x1D000,
data_b 0x1D008, overlap 0x1D004, probe 0x11A0), the
executable-page enable routes through the verified hook
coordinator and the target's own protocol executes the
patched probe entry 0x46474849 with exactly one journal, and
the dedicated recorded live-close fence holds (a blocked
live close on a third owned target refuses with a `False`
return and the exact "code-patch-restore-mismatch" reason,
touches nothing in the target and preserves
`state.lock` / `session.json` / `state.json` / the
`enabled`-state executable journal across the target exit).
Machine note: on this VM the x86 target launches only from
an elevated parent - a non-elevated `CreateProcess` fails
with Win32 740 (the name + architecture launch-block
heuristic: any x86 executable with a "patch"-like name was
refused regardless of content, path, parent or caller
context, while x64 binaries with the same names, x86 with
clean names and "dispatch" launched fine); the SAC
first-launch hypothesis is refuted (SAC registry state off
/ never enabled, no SAC operations log, no block events,
prompt approval ineffective) and AppLocker / WDAC / SRP are
absent or empty, no MOTW, no elevation manifest, no
third-party AV/EDR; Windows Defender behavior monitoring is
the active enforcer on this VM, a Defender exclusion for the
fixture process + the run paths was added and read back as
registered during the clearance, and the elevated
source-runtime run is the recorded evidence; the frozen
re-runs (the generated trainers, `frozen_runtime: true`) of
both architectures ran at the 0.52.2 release cut (2026-11-24);
+24 tests (`tests/test_native_codepatch_probe.py`
18 + `tests/test_native_codepatch_launcher.py` 6); full main
suite 5,227 OK / 36 expected skips; catalog unchanged
(`blocked-catalog-luacall-binding`): 117,616 supported / 193
blocked (the lane touches no table-parsing path; the release
allowlist in `tools/native_build.py` gains the two codepatch
CTs + the `tests/windows/codepatch_fixture` directory); see
the ledger section "Windows code-patch fixture runtime
evidence (2026-11-16 + 2026-11-20, owned code-patch gate
verified in the source runtime, x64 + x86)" in
documentation/native-progress.md and the verified-gates
record in `tests/windows/codepatch_fixture/README.md`.
Post-0.52.1 (2026-11-21, lane work - no release cut): the ROG
Ally field observation + the code-signing pipeline
verification (see the ledger section "Code-signing pipeline
field verification + two production re-proof fixes
(2026-11-21, post-0.52.1, no release cut)" in
documentation/native-progress.md): the 0.47 signing pipeline
is mechanically proven end-to-end on this machine (SDK
signtool 10.0.26100.0 x64, self-signed test PFX 2,638 B
CN=CT2Trainer Sign Test RSA 2048 sha256
`7980b5126f6031a8d042406353b1e5b2286b6b4c220f1074f55206d2be3988d3`,
RFC3161 timestamp via the documented default
`http://timestamp.digicert.com`) - both 0.52.1 artifacts
signed + re-proofed (frozen master 17,074,203 B ->
17,081,584 B sha256
`bd122cb2a2bed2ed01f3fbc770347e6da6d8c94c13db107424ba7aa418f695a1`;
frozen string-x64 trainer 16,923,275 B -> 16,930,656 B sha256
`46414630a7234149ccd3e69336c8816dd439fb733e6640c1d4f536d190bafb38`),
the PyInstaller cookie is unchanged, the embedded plan is
identical in canonical sha256 behind the appended certificate
table, the signed master boots, and the field block stays
diagnosed as Smart App Control (before any code executes -
the requested UAC elevation cannot clear it); two production
re-proof defects fixed (fail-closed, +5 tests in
`tests/test_native_code_signing.py`), full main suite 5,232
OK / 36 expected skips, catalog unchanged at the
`blocked-catalog-luacall-binding` baseline; the durable SAC
fix stays a user-supplied trusted-CA PFX through the
documented environment contract (self-signed does not clear
SAC, per the 0.47 record) - the signed release cut activates
once the certificate is in hand; the frozen re-runs of the gates
ran at the 0.52.2 release cut (2026-11-24).
Superseded 0.52.1 build:
`native-20261115T181026Z-00f5dfe8` (0.52.1, cut
from `main` @ `dc138e0`, 2026-11-15; in-build suite 5,203 OK / 36
expected skips, `ce_inputs: []`, `runtime_unverified` deliberately kept
per gate; source ZIP `CT2Trainer-0.52.1-source.zip` sha256
`c65883bf5a5161a0e4846ba4ed9a5c1725678ec363b94728f4d1dbbe603723a6`
(14,763,924 bytes) - carries the global-gate frozen-trainer
launcher pair (`src/ct2trainer/native/launcher.py` +
`tests/test_native_global_launcher.py`), the release allowlist fix
(`tools/native_build.py`: the two global gate CTs + the
`tests/windows/global_fixture` directory) and the string-fixture
re-pin (`string_probe.py`) - and
portable ZIP `CT2Trainer-0.52.1-windows-portable.zip` sha256
`35b43cc56da28fc29b7663ee3efb61a953f4b085496176b21016365a1f26056e`
(49,918,368 bytes; the frozen `CT2Trainer-Master.exe` (sha256
`bd0388cbe45b350ee11117b99e55262ade6906e81e72e28c286fa1e3ddfe8316`,
17,074,203 bytes) ships next to the converter)). 0.52.1 ships the
global-gate frozen-trainer launcher pair (the
`--global-fixture-target` / `--global-fixture-report` pair in
`launcher.py` in the house pattern - the global gate has no
string-style plan-load failure reservation: an orphan flag or a
mixed gate is refused before the plan is read, exit 2, a frozen
embedded-plan failure is exit 2 without reserving a report, the
report reserved by `global_probe.run_probe`) + the string-fixture
re-pin (the pin build had been cleaned; rebuild
`native-string-fixture-20261115T174324Z-45f4` from the unchanged
source, both string gates re-verified 14/14 in the source
runtime) + the release allowlist fix; the frozen re-runs of the
string (x64 + x86), x86 debug-hook, hook + Lua-record and global
(x64 + x86) gates re-ran at the release cut on the 0.52.1
template stub (sha256
`df004f1afeea2d73fffe1747bb24e8139318311ac59893ea65759a9bf365e040`)
- all seven frozen trainers passed with `frozen_runtime: true`
(14/14 string per architecture, 6/6 x86 debug-hook, 7/7 hook,
4/4 Lua-record, 14/14 global per architecture; x86 / hook /
Lua-record plan identity identical to the source runtime; see the
0.52.1 content section and the "0.52.1 release build record"
section in documentation/native-progress.md); the build ran
unsigned by default (`code_signing` report: signed false /
not-configured) and the signed path activates with a
user-supplied trusted-CA PFX; catalog unchanged
(`blocked-catalog-luacall-binding`): 117,616 supported / 193
blocked (zero delta vs the 0.52 baseline - this cycle touches no
table-parsing path; the remaining 193 blocked rows are the
documented design / gate residuals of the 0.51 residual census,
unchanged). Superseded 0.52 build:
`native-20261115T070952Z-14405931` (0.52, cut
from `main` @ `26e6ebc`, 2026-11-15; in-build suite 5,197 OK / 36
expected skips, `ce_inputs: []`, `runtime_unverified` deliberately kept
per gate; source ZIP `CT2Trainer-0.52-source.zip` sha256
`4ab1445befb795a40387d6ab69b0bf7b5f333b73cd62d2769b3083cab6969a7b`
(14,729,777 bytes) - carries the owned luacall binding
(`src/ct2trainer/native/luacall_binding.py` +
`tests/test_native_luacall_binding.py`) - and
portable ZIP `CT2Trainer-0.52-windows-portable.zip` sha256
`2009c3f1a959766ab793c6b6b57d89dcfb27143b4b1a8c03b78665d450fbd2cf`
(49,899,983 bytes; the frozen `CT2Trainer-Master.exe` (sha256
`29f99e7a069a5a51d03b765ff40d8573684ba3567ec48f4f85fcc26722895903`,
17,072,825 bytes) ships next to the converter)). 0.52 ships the owned
luacall binding + the Windows scan-fixture lane (the production
`luacall_binding_factory` behind the engine's
`_require_luacall_binding` gate - the owned reviewed nth-AOB helper
route for records whose AA envelope carries `luaCall(...)`
references, wired at the standalone trainer / Master trainer /
scan-gate construction sites, engine default stays fail-closed; the
scan fixture re-pin + the owned process/nth scan gate verified in the
source runtime - both the x64 and x86 reports
`ct2trainer-owned-scan/v1` passed, 8/8 checks each, `ce_inputs: []`,
`owned_markers_absent: true` - and the frozen scan gate re-run at the
release cut on the 0.52 template - the two frozen scan trainers
regenerated with the new template stub (sha256
`23e8fed027b0e50f5bc1f81f7b7b626b6df951f5de8ba2a0e7c43fefbbf2d4a9`),
both reports passed 8/8, plan identity identical to the source
runtime; see the 0.52 content section and the "Windows scan fixture
runtime evidence" section in
documentation/native-progress.md); the build ran unsigned by default
(`code_signing` report: signed false / not-configured) and the signed
path activates with a user-supplied trusted-CA PFX; catalog remeasure
`blocked-catalog-luacall-binding`: 117,616 supported / 193 blocked
(zero delta vs `blocked-catalog-051-residual`: record-level diff per
table - zero count diffs, zero newly blocked, zero unblocked, zero
reason changes, all 151 tables byte-identical - the binding + wiring
touch no table-parsing path; the remaining 193 blocked rows are the
documented design / gate residuals of the 0.51 residual census,
unchanged). Superseded 0.51 build:
`native-20261115T023110Z-4ed2835e` (0.51, cut
from `main` @ `35542f4`, 2026-11-15; in-build suite 5,184 OK / 36
expected skips, `ce_inputs: []`, `runtime_unverified` deliberately kept
per gate; source ZIP `CT2Trainer-0.51-source.zip` sha256
`a1cc1b3eb33aca8ff7a041d999f5714a84aec238e782f396f5e6eb7385d4f525`
(14,717,423 bytes) - carries the post-0.50 residual-census
ratification lane (`tests/test_native_residual_ratification.py`) - and
portable ZIP `CT2Trainer-0.51-windows-portable.zip` sha256
`53923298adf229d526995274c98f3bd7476d124ca2d0fc13577392571395a675`
(49,894,393 bytes; the frozen `CT2Trainer-Master.exe` (sha256
`1dff59f006370da718ecf343e66d6cdf78ad7b462bb7468348a4dbbdeb5893bb`,
17,071,049 bytes) ships next to the converter)). 0.51 ships the
post-0.50 residual-census ratification lane (tests only, zero catalog
delta: the five remaining unrated residual classes of the 193-row
census pinned as blocked by design with counter-proofs; see the 0.51
content section in documentation/native-progress.md); the build ran
unsigned by default (`code_signing` report: signed false /
not-configured) and the signed path activates with a user-supplied
trusted-CA PFX; catalog remeasure
`blocked-catalog-051-residual`: 117,616 supported / 193 blocked
(zero delta vs `blocked-catalog-050-provider21`: record-level diff
per table - zero count diffs, zero newly blocked, zero unblocked,
zero reason changes, all 151 tables byte-identical; every remaining
residual row is now covered by a documented gate or a 0.44-0.51
ratification lane). Superseded 0.50 build:
`native-20261114T223759Z-086989d6` (0.50, cut
from `main` @ `4f747ce`, 2026-11-14; in-build suite 5,171 OK / 36
expected skips, `ce_inputs: []`, `runtime_unverified` deliberately kept
per gate; source ZIP `CT2Trainer-0.50-source.zip` sha256
`79c841e9bd7978fdc954a783f7f6989b79d82da9d10a95c35e66a20b7ee6520b`
(14,709,622 bytes) - carries the Provider-21 parity lane
(`aa_program.py` + `aa.py` + `compiler.py` +
`tests/test_native_provider21_ratification.py` + the re-pins in
`tests/test_native_aa_named_refusals.py` /
`tests/test_native_aa_literals.py` /
`tests/test_native_rt42_runtime_provider.py` /
`tests/test_native_assembler.py` /
`tests/test_native_global_engine.py`) - and portable ZIP
`CT2Trainer-0.50-windows-portable.zip` sha256
`fc89315877b0c60b53db8bde568e0c751002f0912e9ad1726f6373eb50f59187`
(49,891,552 bytes; the frozen `CT2Trainer-Master.exe` (sha256
`417708d985bfb0f84530b0fe3703aa7788db81e10e48915218fc875cf236aab6`,
17,071,577 bytes) ships next to the converter)). 0.50 ships the
Provider-21 parity lane (the two CE 7.5 source parity fixes - the
comment-to-EOF parity in the AA source scanners and the shared-
globalalloc keep-first collapse in `compiler._dependencies` - plus the
tests-only ratification of the 17 by-design rows of the 21-row "no
unique supported provider" census; see the 0.50 content section in
documentation/native-progress.md); the build ran unsigned by default
(`code_signing` report: signed false / not-configured) and the signed
path activates with a user-supplied trusted-CA PFX; catalog remeasure
`blocked-catalog-050-provider21`: 117,616 supported / 193 blocked (net
-5 vs the 0.49 baseline: exactly the Cyberpunk2077 380/381 `weaponPtr`
dependents + the SonicFrontiers 1337230409 "Pin Ball" provider + its
1337230410/1337230411 `pPinBall` dependents unblocked, zero newly
blocked, zero reason changes, the other 148 tables byte-identical; the
17 by-design rows stay blocked until the documented condition is
met). Superseded 0.49 build:
`native-20261114T184922Z-4b721a9e` (0.49, cut
from `main` @ `20c63c1`, 2026-11-14; in-build suite 5,155 OK / 36
expected skips, `ce_inputs: []`, `runtime_unverified` deliberately kept
per gate; source ZIP `CT2Trainer-0.49-source.zip` sha256
`e2adfb4d6153d0293e1be70e43d15f71a5b8ecd6889b7ecb74ec79cc9179ce24`
(14,699,553 bytes) - carries the shape-3 dynamic-variable Lua symbol
provider lane (`lua_symbol_providers.py` +
`tests/test_native_lua_variable_symbol_providers.py`) and the remaining
class-d user-symbol import ratification
(`tests/test_native_user_symbol_import_remaining.py`) - and portable ZIP
`CT2Trainer-0.49-windows-portable.zip` sha256
`4139bf2079f11ca7fba8c41b1d0c1bd201d146abdd3f8171bbafa18a7a931675`
(49,888,023 bytes; the frozen `CT2Trainer-Master.exe` (sha256
`d3ada53a7ebc6c160be55608046a286ba98028a1858cc2d950a64327a529d63b`,
17,070,681 bytes) ships next to the converter)). 0.49 ships the
FO4 "Player Editor" shape-3 dynamic-variable Lua symbol provider
(the last embedded-Lua symbol provider shape against the
reference tables) + the remaining class-d user-symbol import
ratification (tests only, against the 198-row post-0.48 catalog
census): shape 3 in
`lua_symbol_providers.extract_lua_symbol_providers` - a
record's `{$lua}` registers each entry under its name through a
variable that ranges over a flat literal string array (the
array's string constants are the record's staged provides;
strictly bounded: flat string arrays only, the exact
`local var = ARRAY[i]` single-index binding with a variable
index, one binding per variable, one array definition per
name, same part; out of bound: row tables, numeric or
identifier cells, constant indices, double-index tails, re-
bound variables, unbound arrays, non-local bindings, call
arguments, more than MAX_PROVIDERS derived names - every shape
pinned; registration evidence from preamble + enable lua
parts, release from the disable phase only); the ratification
lane proves the documented `<UserdefinedSymbols>` import path
on the 17 residual class-d value-symbol rows (6
`g_GameLibSystemAssets` / 5 `HeroSystem` / 3 `pGrav` / 2
`MapLastLeftClickCoordinates_Pointer` / 1 Kena three-part
`FreeResources` + `Kena` + `Win64` module-qualified operand -
the full managed name as a single UDS does NOT cover the
decomposition, the progressive remedy names the next missing
part each time): blocked as-is with the exact named message,
supported / unstaged / dependency-free with the import,
byte-exact through the engine; the 2 `HeroHealthVFTable` rows
stay out of scope (encoded embedded-Lua registration with a
`createThread` entry point); the build ran unsigned by default
(`code_signing` report: signed false / not-configured) and
the signed path activates with a user-supplied trusted-CA
PFX; catalog remeasure `blocked-catalog-049-variable`:
117,611 supported / 198 blocked (net -8 vs the 0.48
baseline: exactly the 8 Fallout4 "Player Editor" stat rows
unblocked, zero newly blocked, zero reason changes, the other
150 tables byte-identical; the 17 class-d rows stay blocked by
design until the user imports the symbols). Superseded 0.48 build:
`native-20261114T133842Z-8ee6999f` (0.48, cut
from `main` @ `5d467dc`, 2026-11-14; in-build suite 5,127 OK / 36
expected skips, `ce_inputs: []`, `runtime_unverified` deliberately kept
per gate; source ZIP `CT2Trainer-0.48-source.zip` sha256
`feb962e5628027f1ee79acbc16cb10a4dfe36ef5a3de7f4cf4f3681d9cc37f0b`
(14,682,168 bytes) - carries the trailing-offset parity lane
(`address_expression.py` +
`tests/test_native_trailing_offsets.py`) - and portable ZIP
`CT2Trainer-0.48-windows-portable.zip` sha256
`352069d184e93f19f6ec56ce9236bedc168b09e66da7c3ac2af15b13615d3a85`
(49,879,644 bytes; the frozen `CT2Trainer-Master.exe` (sha256
`9843d6dce2445af3bc883f12b9b16f6b5eb2c0fbfa2c86dae986c77c65383f10`,
17,066,255 bytes) ships next to the converter)). 0.48 ships the
CE 7.5 trailing-offset parity (compatibility lane against the
210-row post-0.47 catalog census): the bounded grammar extension
in `address_expression.parse_expression` - one value atom directly
after a `]` token takes an implicit `+` operand (the CE
`TSymhandler` contract: `[mats]20` reads as `[mats]+0x20`, hex
default; explicit operators, a closing/repeating bracket, a `(`
and 0x/$/#-prefixed numbers stay refused; byte-stable: no
supported expression can contain `]` followed by a value atom) -
closing the four qt-ds-1 / qt-ds-2 `[mats]20` / `[mats]28` value-
record rows while the rayman `Made by` string address stays
blocked by design; the build ran unsigned by default
(`code_signing` report: signed false / not-configured) and the
signed path activates with a user-supplied trusted-CA PFX; catalog
remeasure `blocked-catalog-048-trailing`: 117,603 supported /
206 blocked (net -4 vs the 0.47 baseline: exactly the four
qt-ds rows unblocked, zero newly blocked, zero reason changes, the
other 149 tables byte-identical). Superseded 0.47 build:
`native-20261114T011046Z-ee5cecee` (0.47, cut
from `main` @ `6e1940e`, 2026-11-14; in-build suite 5,108 OK / 36
expected skips, `ce_inputs: []`, `runtime_unverified` deliberately kept
per gate; source ZIP `CT2Trainer-0.47-source.zip` sha256
`436a330aeceb70a51c2fc5585085a133b25ea6f05aedcdfa25353aa9042d436d`
(14,675,788 bytes) - carries the code-signing package
(`code_signing.py` + `tests/test_native_code_signing.py` + the
bundle footer-scan) and the SAC user docs (`usage.md` section 8,
`build.md` section 3) - and portable ZIP
`CT2Trainer-0.47-windows-portable.zip` sha256
`146ee9cd99a12865779ba1daff9e66fa0855be20a7a847d0bd47a513e74bc3a5`
(49,879,105 bytes; the frozen `CT2Trainer-Master.exe` (sha256
`a770f9689a5744a49aa26ec911437f0fcd09a05631e85edcfea92061b6658453`,
17,066,832 bytes) ships next to the converter)). 0.47 ships the
optional code signing for the frozen and generated trainer
executables (Smart App Control handling, the field block observed
2026-11-14 on the 0.46 trainer): the environment-driven
`code_signing.py` layer (signtool sign step, the pure
certificate-table re-proof, fail-closed named `sign-…` refusals),
the build-time signing of converter + master (the template
deliberately unsigned), the generation-time signing of every
generated trainer, and the footer-scan `read_embedded_plan` that
finds the plan through the certificate table signtool appends
after the footer; the build runs unsigned by default
(`code_signing` report: signed false / not-configured) and signing
activates with a user-supplied trusted-CA PFX; catalog unchanged
at 117,599 supported / 210 blocked - no table-parsing path
touched. Superseded 0.46 build:
`native-20261113T185658Z-e543af1a` (0.46, cut from `main` @
`b348184`, 2026-11-13; in-build suite 5,071 OK / 36
expected skips, `ce_inputs: []`, `runtime_unverified`
deliberately kept per gate; source ZIP
`CT2Trainer-0.46-source.zip` sha256
`c49323d56d8feab0652f676d86a739fb6204cff6ddeed8e4b326e43020ee4d62`
(14,661,247 bytes) - carries the AA extended-register /
size-keyword parity lane (`aa_program.py` +
`tests/test_native_aa_register_aliases.py`) - and portable ZIP
`CT2Trainer-0.46-windows-portable.zip` sha256
`1b130db71508e42b98c4127ebcec766bc79cd65aabdd563ed59d4b058bfc9fe9`
(49,857,331 bytes; the frozen `CT2Trainer-Master.exe` (sha256
`18306034231d6632ba15f4f23f62e611dd2c9b73e14db634d99f6cdccb7e8857`,
17,069,499 bytes) ships next to the converter)). 0.46 ships the
AA extended-register `l` alias + `dqword` size-keyword parity
(catalog remeasure `blocked-catalog-046-regsize`: 117,599
supported / 210 blocked, net -11 vs `blocked-catalog-lane-b` -
the 9 direct register / size rows + 2 provider cascades
unblocked, zero newly blocked, zero reason changes). Superseded
0.45 build: `native-20261113T144426Z-572d5b30` (0.45, cut
from `main` @ `58d6c8f`, 2026-11-13; in-build suite 5,062 OK / 36
expected skips, `ce_inputs: []`, `runtime_unverified` deliberately kept
per gate; source ZIP `CT2Trainer-0.45-source.zip` sha256
`3bdd783359623d273de15e90f4f0acc524d3ecbda64f925c3cf59de9d4e27416`
(14,657,388 bytes) - carries MT-34 (`engine.py` + `ui.py` +
`tests/test_native_hotkey_session_switch.py`) and the
trainer-tick-sound field fix (`trainer_sounds.py` +
`tests/test_native_trainer_sounds.py`) - and portable ZIP
`CT2Trainer-0.45-windows-portable.zip` sha256
`58bac73098b219e3049668b55877e8a3e4fd758e6e1917b058da128e416eb4e2`
(49,854,120 bytes; the frozen `CT2Trainer-Master.exe` (sha256
`f882add64b2fc0f9d66cb88ed2142684e71736de326b28f72ddb007186aa2d05`,
17,069,125 bytes) ships next to the converter)). 0.45 ships the
per-session hotkey switch (MT-34) + the trainer-tick-sound field
fix; catalog unchanged at `blocked-catalog-lane-b` (117,588
supported / 221 blocked - MT-34 and the sound fix touch no
table-parsing path). Superseded 0.44 build:
`native-20261112T233337Z-1dc678c6` (0.44, cut
from `main` @ `ab11893`, 2026-11-13; in-build suite 5,049 OK / 36
expected skips, `ce_inputs: []`, `runtime_unverified` deliberately kept
per gate; source ZIP `CT2Trainer-0.44-source.zip` sha256
`026886a700282a56c40568f30d2a4ebc57d6390a59cd59c42fd3f7f5dc8d49ff`
(14,648,668 bytes) - carries the three-lane cycle
(`tests/test_native_baseaddress_import.py` + `lua_program.py` +
`lua_symbol_providers.py` +
`tests/test_native_lua_define_providers.py` +
`tests/test_native_lua_name_list_providers.py` + `compiler.py` +
`engine.py` + `tests/test_native_staged_pointer_chain.py`) - and
portable ZIP `CT2Trainer-0.44-windows-portable.zip` sha256
`656bf7106fd86a5a21532cf476b91f82cfafe2287ef5bf3d3ba41b6d2d9d6f36`
(49,885,729 bytes; the frozen `CT2Trainer-Master.exe` (sha256
`02e4731ef30ce320f71594f37cb176402be64849a90656c785d474dbc50d6112`,
17,084,284 bytes) ships next to the converter)). 0.44 ships the
deferred compatibility-lane cycle (Lane C `BaseAddress` import proof,
Lane A dynamic Lua symbol registration, Lane B nested
relative-address staging) closing all three lead cases of the
537-blocked census. Superseded 0.43 build:
`native-20261111T184600Z-3bf9d8aa` (0.43, cut
from `main` @ `0df2607`, 2026-11-11; in-build suite 5,011 OK / 36
expected skips, `ce_inputs: []`, `runtime_unverified` deliberately kept
per gate; source ZIP `CT2Trainer-0.43-source.zip` sha256
`c0011d10a5a60b78067b0cdd1a622a134088fee325ac4d544efd3ec8101438ca`
(14,617,762 bytes) - carries the MT-32/MT-33 tray + geometry
(`master_trainer/tray.py` + `master_trainer/window_geometry.py` +
`tests/test_native_master_tray_geometry.py`) and the TGC field fix
(`memory.py` + `engine.py` + `hooks.py` +
`tests/test_native_tgc_field_fix.py`) - and portable ZIP
`CT2Trainer-0.43-windows-portable.zip` sha256
`dc7a4062b56be99ea887a77ffd23e7c2c1ff38935e471d7f124ed4d775a022e9`
(49,849,139 bytes; the frozen `CT2Trainer-Master.exe` (sha256
`4846d7568ef4eba091261b21e678c13ab5cecbbf3468a0a57ba30d84fc7e91a4`,
17,072,494 bytes) ships next to the converter)). 0.43 ships the
Master Trainer minimize-to-tray + window-geometry persistence
(MT-32/MT-33) and the TGC field fix (transient target-memory reads no
longer block the engine). Superseded
0.42 build: `native-20261111T044023Z-04112d15` (0.42, cut
from `main` @ `377f760`, 2026-11-11; in-build suite 4,926 OK / 35
expected skips, `ce_inputs: []`, `runtime_unverified` deliberately kept
per gate; source ZIP `CT2Trainer-0.42-source.zip` sha256
`f44d248303b302b8621e80efc7c6faff476d0f27887b729546bf42c639839415`
(14,589,013 bytes) - carries the CE 7.5 cleanup parity
(`aa_program.py` + `compiler.py` +
`tests/test_native_aa_cleanup_parity.py`) and the API-export
registry extension (`sleep` / `showwindow`) - and portable ZIP
`CT2Trainer-0.42-windows-portable.zip` sha256
`305832ddc03487542c9a889e150b96f45c1576fa5e56819276da54b9388a5c40`
(49,821,481 bytes; the frozen `CT2Trainer-Master.exe` (sha256
`35389c7611715b494418b2c5bcdbd48e84f8d55a55f3deab556c4aa4d6aefd1c`,
17,051,026 bytes) ships next to the converter)). 0.42 ships the
CE 7.5 cleanup parity (unowned cleanup names are a silent no-op,
recorded in `unowned_cleanup_dropped`; live cross-record names keep
the named handover refusal) and the API-export registry extension
(`sleep` / `showwindow`). Superseded
0.41 build: `native-20261110T210856Z-5811040c` (0.41, cut
from `main` @ `c724a7e`, 2026-11-10; in-build suite 4,917 OK / 35
expected skips, `ce_inputs: []`, `runtime_unverified` deliberately kept
per gate; source ZIP `CT2Trainer-0.41-source.zip` sha256
`05ef6cabca08adcca8a084722581b7d553966e480e28274a4a72f4b31b9c1964`
(14,580,191 bytes) - carries the AA typed-constant package
(`aa_program.py` +
`tests/test_native_aa_typed_constants.py`) and the
digit-leading-label CE 7.5 parity fix
(`tests/test_native_aa_digit_labels.py`)
- and portable ZIP
`CT2Trainer-0.41-windows-portable.zip` sha256
`533bee676d0ed5c487741cb4919af8f4370f2bee1c5c26181ed5f3f0c3753a77`
(49,814,303 bytes; the frozen `CT2Trainer-Master.exe` (sha256
`ce07c42cf22c57eeeffa08be74ff562d3a7dcfca5f4c2d14121c784acd24c6f`,
17,049,435 bytes) ships next to the converter)). 0.41 ships the
AA typed-constant package (the CE `StrToQWordEx` contract)
and the digit-leading-label CE 7.5 parity fix. Superseded
0.40 build: `native-20261110T093203Z-82c49872` (0.40, cut
from `main` @ `e611e9e`, 2026-11-10; in-build suite 4,879 OK / 35
expected skips, `ce_inputs: []`, `runtime_unverified` deliberately kept
per gate; source ZIP `CT2Trainer-0.40-source.zip` sha256
`46ad5dd9f9adc872e320dd4aec2362e007020ae879bba0cc8fe0621e44c34c40`
(14,569,029 bytes) - carries the MT-31 process
identification (`process_watch.py` enrichment layer +
`tests/test_native_master_ui_mt31.py`) and the bounded
transient-write retry
(`tests/test_native_memory_write_retry.py`)
and the reviewable `master_trainer/UI.md` - and portable ZIP
`CT2Trainer-0.40-windows-portable.zip` sha256
`5075586c7b0f3251749c8e3e60ec0db7fea251db39190b59b63273a4e9b10bd6`
(49,809,535 bytes; the frozen `CT2Trainer-Master.exe` (sha256
`52f6da1cebfc44a0dc791d4b5758112342b5a1d42c9fc9656901a16d1a5eb03f`,
17,048,910 bytes) ships next to the converter)). 0.40 ships the
Master Trainer process identification in picker + details
(MT-31) and the bounded zero-transfer transient-write retry in
`memory.py`. Superseded
0.39 build: `native-20261110T051241Z-57bf7d47` (0.39, cut
from `main` @ `17a22f7`, 2026-11-10; in-build suite 4,833 OK / 30
expected skips, `ce_inputs: []`, `runtime_unverified` deliberately kept
per gate; source ZIP `CT2Trainer-0.39-source.zip` sha256
`14163e7475477c177be339d06fd5ba7b9a7016667405669b084faed25035a923`
(14,549,960 bytes) - carries the MT-29 auto-load policy
(`table_autoload.py` pure layer + `table-autoload.json` schema 1,
`tests/test_native_master_autoload.py` +
`tests/test_native_master_ui_mt29.py`), the MT-30 state folder /
debug log quick access (`state_access.py` pure layer,
`tests/test_native_master_ui_mt30.py`) and the bounded
transient-read retry (`tests/test_native_memory_read_retry.py`)
and the reviewable `master_trainer/UI.md` - and portable ZIP
`CT2Trainer-0.39-windows-portable.zip` sha256
`7d5d7903f1be5df0eac0f1067d5c2ca596321a41ea37381e033e5deb175ec8b6`
(49,800,752 bytes; the frozen `CT2Trainer-Master.exe` (sha256
`e0db5b2e2f41ec816089486ca57a2c0b1424523e7ee8450335053923ab629e47`,
17,042,819 bytes) ships next to the converter)). 0.39 ships the
Master Trainer per-table auto-load policy (MT-29), the state
folder / debug log quick access (MT-30) and the bounded
transient-read retry in `memory.py`. Superseded
0.38 build: `native-20261109T211151Z-03e89050` (0.38, cut
from `main` @ `da1e68f`, 2026-11-09; in-build suite 4,760 OK / 30
expected skips, `ce_inputs: []`, `runtime_unverified` deliberately kept
per gate; source ZIP `CT2Trainer-0.38-source.zip` sha256
`e2b466adc7abfb191bbd2b50f8304739a1e82cbf487099d4ecd6fd77cc3f3d0c`
(14,521,497 bytes) - carries the --force forced start (`state_force.py`
pure layer + `tests/test_native_state_force.py` +
`tests/test_native_master_force.py`) and the reviewable
`master_trainer/UI.md` - and portable ZIP
`CT2Trainer-0.38-windows-portable.zip` sha256
`df5ccfa373c8f5deb6be85f36e75941a1c0b3a9f13afae23c03f1644f9290fc4`
(49,781,948 bytes; the frozen `CT2Trainer-Master.exe` (sha256
`5d2cc5544eb6a29f1c3283f05e809e392d0038a1f59456c9d52f0356e519231d`,
17,026,316 bytes) ships next to the converter)). 0.38 ships the --force
forced start for the documented SteamOS state-lock dead end. Superseded
0.37 build: `native-20261109T154005Z-4ad8e339` (0.37,
cut from `main` @ `27dbf0d`, 2026-11-09; in-build suite 4,733 OK / 30
expected skips, `ce_inputs: []`, `runtime_unverified` deliberately
kept per gate; source ZIP `CT2Trainer-0.37-source.zip` sha256
`a49bdd7d738de9551a1d971430ed9f7b0a212ec0d4a2afd8667e1f87ec61d301`
(14,506,715 bytes) - carries the MT-28 per-table process
binding persistence (`table_attach.py` pure layer +
`table-attach.json` schema 1,
`tests/test_native_master_attach.py` +
`tests/test_native_master_ui_mt28.py`) and the reviewable
`master_trainer/UI.md` - and portable ZIP
`CT2Trainer-0.37-windows-portable.zip` sha256
`5cdb23b24c0757cb047ddd72ae673614fc6bccee960747079849fe325785c3ce`
(49,762,223 bytes; the frozen `CT2Trainer-Master.exe`
(sha256 `c2a1a6948fa28248d36a6defa5a116867620261e55bdcfe1e144cd301060a9de`,
17,017,090 bytes) ships next to the converter)).
0.37 ships the Master Trainer per-table process binding
persistence (MT-28). Superseded 0.36 build: `native-20261109T114726Z-15c3d9ab` (0.36,
cut from `main` @ `d071884`, 2026-11-09; in-build suite 4,665 OK / 30
expected skips, `ce_inputs: []`, `runtime_unverified` deliberately
kept per gate; source ZIP `CT2Trainer-0.36-source.zip` sha256
`79464f02cd71492763656ca0ff3283a240c3579b9f52df3bcc18857dabb3d1be`
(14,490,858 bytes) - carries the MT-21 multi-column trainer grid
(`ui_rows.py` grid pure layer + `master_state.py` schema 9,
`tests/test_native_ui_grid.py` +
`tests/test_native_master_ui_mt21.py`) and the reviewable
`master_trainer/UI.md` - and portable ZIP
`CT2Trainer-0.36-windows-portable.zip` sha256
`089fc92b0c5758ba758fdc88bb92e11d8e3b3e36c28d04231f27b3eeaecceac0`
(49,751,886 bytes; the frozen `CT2Trainer-Master.exe`
(sha256 `07ebef319b55d686c4f76cdb6f07440a2b4934fc8943f9f72b402d62c4c49fe8`,
17,006,463 bytes) ships next to the converter)).
0.36 ships the Master Trainer multi-column trainer grid (MT-21).
Superseded 0.35 build: `native-20261109T054146Z-c5f18494` (0.35,
cut from `main` @ `65d8fbe`, 2026-11-09; in-build suite 4,610 OK / 30
expected skips, `ce_inputs: []`, `runtime_unverified` deliberately
kept per gate; source ZIP `CT2Trainer-0.35-source.zip` sha256
`575ee8ad6f0864bd8ff39f3ae547bb629d5c128938cff792e9c4fb7362fbcdac`
(14,474,384 bytes) - carries the MT-27 per-table notes / tags
(`table_notes.py` pure layer + `table-notes.json` schema 1,
`tests/test_native_master_notes.py`) and the reviewable
`master_trainer/UI.md` - and portable ZIP
`CT2Trainer-0.35-windows-portable.zip` sha256
`488d7453ca0433f843c1e46a2241142347aa2ee41390ed334d6068ed30e42d34`
(49,737,899 bytes; the frozen `CT2Trainer-Master.exe`
(sha256 `0c53908c267746cabd74e1ef091daa35d31eb94c4d0accc6401085d7e8c59ccc`,
16,999,124 bytes) ships next to the converter)).
0.35 ships the Master Trainer per-table notes / tags (MT-27).
Superseded 0.34 build: `native-20261109T024143Z-a5457911` (0.34,
cut from `main` @ `dc00343`, 2026-11-09; in-build suite 4,543 OK / 30
expected skips, `ce_inputs: []`, `runtime_unverified` deliberately
kept per gate; source ZIP `CT2Trainer-0.34-source.zip` sha256
`0d0a0849a90171f64eaf5b55ec06ec1d9117d02d5330895dcb4279e26f73b0f5`
(14,455,170 bytes) - carries the MT-26 multi-root table index
(`table_index.py` `RootIndexSet` + schema-2 index set,
`master_state.py` schema 8,
`tests/test_native_master_ui_mt26.py`) and the reviewable
`master_trainer/UI.md` - and portable ZIP
`CT2Trainer-0.34-windows-portable.zip` sha256
`ade1ecc520ddbeaf6886e1b195fc6e2886a5f9cbeaa64b15f9ac5679420f5054`
(49,719,386 bytes; the frozen `CT2Trainer-Master.exe`
(sha256 `606ea2287eb9f787308d862c18209076ee42e4f7a4ae88fcb93bf8f22edcb6f6`,
16,983,514 bytes) ships next to the converter)).
0.34 ships the Master Trainer multi-root table index (MT-26).
Superseded 0.33 build: `native-20261108T200230Z-b0167049` (0.33,
cut from `main` @ `6e71739`, 2026-11-08; in-build suite 4,499 OK / 30
expected skips, `ce_inputs: []`, `runtime_unverified` deliberately
kept per gate; source ZIP `CT2Trainer-0.33-source.zip` sha256
`4528d1d0f2ee269fb2ee7ec470d9e9711b3c284bffe6cf582f7dafa7431756f2`
(14,433,388 bytes) - carries the MT-25 auto-rescan
(`master_state.py` schema 7, the 30 s auto-rescan tick,
`tests/test_native_master_ui_mt25.py`) and the reviewable
`master_trainer/UI.md` - and portable ZIP
`CT2Trainer-0.33-windows-portable.zip` sha256
`5e0244791b6f31a2e2219d5c33541c978ca4c0d399c8e7a234cb0c16e8ccb3d7`
(49,703,149 bytes; the frozen `CT2Trainer-Master.exe`
(sha256 `59961d511d3964b075c968a3c577117ffa235970d65976f66d7e34e0eae010a9`,
16,968,879 bytes) ships next to the converter).
0.33 ships the Master Trainer table folder auto-rescan (MT-25).
Superseded 0.32 build: `native-20261108T100731Z-a1d311e5` (0.32,
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
16,966,114 bytes) ships next to the converter). Superseded 0.31 build:
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
