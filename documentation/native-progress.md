# CT2Trainer: Native progress ledger

**Central tracking:** all open gaps, goals, work packages, corpus cases and
the measurement snapshot are tracked in one place:
[`plans/TRACKING.md`](../plans/TRACKING.md). This ledger keeps the
confirmed-state detail (builds, suites, acceptance records); when in doubt
about current status, check the tracker first.

Status: **November 4, 2026** (0.30 released - build
`native-20261104T131114Z-11522f68` cut from `main` @ `2fbca94`,
2026-11-04 -
Master Trainer table details + live load-gate preview (MT-22)
(online-evaluated in `master_trainer/ROADMAP.md`, the "0.30 table
details + load-gate preview" section): the waiting-view row context
menu offers "Table details" first - the read-only Toplevel with the
indexed facts for the table (path, folder, size, modified, bound
processes, index status, pin, last used, running PIDs, content sha)
plus the on-demand `gate_table_for_load` re-check - the same pass
MT-9 runs at load time, so a refusal shows the stable named code +
displayable detail (a stale / changed / unreadable table is
explained at inspection time, not only at load time); the pure
`table_details.py` row builder; single window, lift on second open,
closed on trainer entry; the only I/O is the bounded gate re-check
under the load limit); +16 tests; full main suite 4,386 OK / 30
expected skips; catalog zero delta `blocked-catalog-030-details`;
root-direct on `main`, `VERSION` 0.30 + CHANGELOG entry in the same
change); record below. Superseded 0.29 (build
`native-20261104T094808Z-50af0517` cut from `main` @ `de3e4ff`,
2026-11-04 - Master Trainer UI/UX revamp MT-19/20 (user field
request 2026-11-04): MT-19 trainer-focus mode (the whole waiting
view lives in one container frame destroyed on trainer entry - the
trainer row grid owns the full window, rebuilt whole on the way
back; the trainer-constructor failure path rebuilds the waiting
view before failing the load) + MT-20 discoverability (the
read-only "UI flow" header button - the in-app copy of the
reviewable `master_trainer/UI.md`, F5 re-scan from anywhere in the
waiting view, the initial table-list focus, the "Retry load"
re-arm in the status bar; the reviewable full-flow document ships
in the source ZIP); online-evaluated in `master_trainer/ROADMAP.md`
(the "0.29 trainer-focus + discoverability" section); the deferred
multi-column trainer grid is documented as candidate MT-21
(separate cycle - the single-column canvas grid is the validated
touch-first design shared with the standalone trainer); +13 tests;
full main suite 4,370 OK / 30 expected skips; catalog zero delta
`blocked-catalog-029-trainer-focus`, released as build
`native-20261104T094808Z-50af0517`); record below. Superseded
0.28 (build
`native-20261103T161621Z-ea8fde2f` cut from `main` @ `d7f4cf0`,
2026-11-03 - Master Trainer pinned/favorite tables MT-18
(`master-settings.json` schema 4 -> 5: the persisted pin set -
relative paths, most recent pin first, cap 25; the row context
menu toggle, pinned tables float to the top of the list view and
to the top of their process group, pin marker in the detail
column; pure `pin_tables` layer, named refusals); the adopted
0.28 candidate recorded in `master_trainer/ROADMAP.md` (the 0.27
follow-up research); +15 tests; full main suite 4,357 OK / 30
expected skips; catalog zero delta `blocked-catalog-028-pin`,
released as build `native-20261103T161621Z-ea8fde2f`); record
below. Superseded 0.27 (build
`native-20261103T145543Z-b29b3688` cut from `main` @ `8aa0815`,
2026-11-03 - Master Trainer waiting-view settings persistence
MT-16 + process-grouped waiting view MT-17; +22 tests, full main
suite 4,342 OK / 30 expected skips, catalog zero delta
`blocked-catalog-027-view`, released as build
`native-20261103T145543Z-b29b3688`); record below. Superseded
0.26 (build `native-20261103T112811Z-59a6b3d5` cut from `main` @
`c114ec2`, 2026-11-03 - Master Trainer waiting-view usability
MT-13/14/15: search/filter/sort through the new pure
`table_filter.py` layer, keyboard load flow, rolling recent tables
in `master-settings.json` schema 3 +
Size/Modified/Last-used columns; plus the live-target takeover
field fix; +61 tests, full main suite 4,320 OK / 30 expected
skips, catalog zero delta `blocked-catalog-026-master-ui`,
released as build `native-20261103T112811Z-59a6b3d5`); record
below. Superseded 0.25 (build
`native-20261103T062439Z-f4c16be9` cut from `main` @ `a861bfb`,
2026-11-03 - Master Trainer user control MT-10/11/12: explicit
table load,
process picker + persisted attach mode, detach/user attach; online
feature evaluation in `master_trainer/ROADMAP.md`; Tcl test-harness
hardening; in-build reliability fix; +66 tests, full main suite
4,259 OK / 30 expected skips, catalog zero delta
`blocked-catalog-025-master-ui`, released as build
`native-20261103T062439Z-f4c16be9`); superseded 0.24 (trainer tick
sounds, branch `native-0.24-trainer-sounds`,
+21 tests, full main suite 4,193 OK / 30 expected skips, catalog
zero delta `blocked-catalog-024-sounds`, released as build
`native-20261102T102029Z-fe358e35`); superseded 0.23 (build
`native-20261101T145310Z-a160bae4` cut from `main` @ `6e3ec98`):
full Master Trainer roadmap - MT-6 per-table settings sidecar
(keyed by table content sha256, restore-on-load / save-on-close),
MT-7 documented SteamOS/CheatDeck target route (named fail-closed
non-Windows attach refusals, NOT a Linux attach backend), MT-8
frozen `CT2Trainer-Master.exe` now part of every build, MT-9
load-time table compatibility & size gate (stable named refusals,
fail-closed loop guard, no hot-retry), waiting-view observability
(metadata line, live "Running now" line, running/PID tree markers),
ask-on-first-start table-folder parameter (`master-settings.json`
persisted in the state home, explicit folder argument wins) + the
same-day field fixes (placeholder-heading symbol-dependency skip
`28c9b57` +10 tests; SC2 hotkey-bridge field fix 0.22.1 lane merge
`4e9b95b` +11 tests); branch `native-0.23-master-roadmap` +
`native-0.23-load-gate`, main @ `6e3ec98`, +115 tests, in-build
suite 4,176 OK / 30 expected skips, catalog zero delta
`blocked-catalog-023-field-fixes`.
Superseded 0.22, build `native-20261101T075049Z-f32c112d` cut
from `main` @ `2b24a1c` - the 0.22 FO4 field-fix cycle (bounded
automatic re-arm of ScanMiss enable failures (30 s x 10 attempts,
budget reset per (re-)attach, armed set survives target exit) +
manual Try again / Re-attach actions (branch
`native-0.21-fo4-rearm`, merged `main` @ `a12a0b6`, commit
`5704fd2`, +17 tests, full main suite 4,061 OK / 30 expected skips,
zero catalog delta `blocked-catalog-022-rearm`; SC2 0.19
hotkey-bridge field findings recorded, fixes deferred to the next
field-fix cycle; in-build suite 4,061 OK / 30 expected skips,
`ce_inputs: []`). Superseded 0.21, build
`native-20261031T211046Z-14707e12` cut from `main` @ `9a725a8` - the
0.21 feature release (RT-5 complete: items B + E; 0.21 Master
Trainer; in-build suite 4,044 OK / 30 expected skips,
`ce_inputs: []`). Superseded 0.20.1, build
`native-20261031T104114Z-d64ae4c2` cut from `main` @ `080128c` - the
0.20.1 release-content re-cut of the 0.20 branding-icon release
(corrected 0.20 changelog suite line, `blocked-catalog-020-icons`
cited; no code or asset changes; in-build suite 3,854 OK / 26
expected skips, `ce_inputs: []`); superseded 0.20, build
`native-20261030T184820Z-b9d6dc07` cut from `main` @ `6298803` - the
branding-icon release (user-provided `CT2Trainer_Generator` icon for
the tool EXE, `Standalone_Trainer` icon embedded in the template
stub, 1024x1024 PNG masters committed, multi-size ICOs rebuilt,
`tests/test_native_icons.py` +4, in-build suite 3,854 OK / 26
expected skips, zero catalog delta `blocked-catalog-020-icons`);
superseded 0.19, build `native-20261030T121918Z-c72dbb38` cut from
`main` @ `fbe626f` - the 0.19 field-fix cycle (Sinking City 2
hotkey-bridge Windows AV fix, value-read observability, `describe`
CLI, South of Midnight staged-options support; +24 tests, in-build
suite 3,850 OK / 26 expected skips, zero catalog delta
`blocked-catalog-019-field`); superseded 0.18, released 2026-10-28,
build
`native-20261028T131208Z-55922918` cut from `main` @ `70c5a61` - the
trainer UI row-details window: "Row details" leads the row context menu
(right-click / long-press), one read-only window with the raw script
source, the plain-language assessment and the concrete actions the
trainer performs per entry, +22 tests, in-build suite 3,767 OK / 25
expected skips, `ce_inputs: []`; superseded 0.17, build
`native-20261027T094839Z-ec6c6f55` cut from `main` @ `ee41630` - the
RT-4.2 runtime provider model (last RT-4 package; catalog remeasure
`blocked-catalog-rt42-main`: 1,351 -> 1,053 blocked of 117,634, 298
rows unblocked, zero newly blocked, 28 reason-only changes) plus the
RT-4.3 address-expression & identifier-dialect merge, the RT-4.5 and
RT-4.6 merges, the trainer UI Scripts view and row context menu, and
the RT-5 item G / F gate ratifications on top of the 0.16.4 field fix
(Sinking City 2 trainer crash observability from the
0.16.3 field test: silent hard exit mid wish-restore with zero
follow-up log events; `arm_crash_reporting()` excepthook/threading-hook/
faulthandler sinks into the opt-in debug log, fail-closed poll guard,
`restore-entry-start` markers; state-lock behavior unchanged) on top of
0.16.3 (build
`native-20261023T065015Z-afbc3eba` cut from `main` @ `6a5ba63` - the
0.16.3 field fix (Sinking City 2 activation failure from the
0.16.2 field test: hook-journal `value_data_ranges` accepted by the
recovery assessment + module-snapshot transient retry with correct
Win32 codes, bounded exponential backoff and architecture-aware
fallback flag) on top of 0.16.2 (build
`native-20261022T160328Z-0423fb21` cut from `main` @ `68eeb00` -
RT-4.1 symbol provider fidelity on `main` (keep-first duplicate-
provider policy, `label()` duplicate-name tolerance, wildcard-cleanup
scoping, catalog remeasure 2,698 -> 1,858 blocked of 117,624, zero
unexplained supported regressions) plus the 0.16.2 field fix - WP-57
hook journal `captured_placeholders` accepted by the recovery
assessment, field finding from the 0.16.1 Sinking City 2 startup
block; 0.16.1 released, build
`native-20261021T161241Z-b0566a25` cut from `main` @ `d1c61f2`;
previous 0.16 field-fix re-cut 2
`native-20261021T123801Z-8c5c4e1e` @ `108170b`,
re-cut `native-20261020T150115Z-c426fb92` @ `7616edb` and first
0.16 run `native-20261020T103508Z-0e3f9d90` @ `809666a` superseded —
0.16.1: Sinking City 2 table-load warnings made accurate (table-version
reference 45 → 46, accurate `{$LUA}`/external-action wording) under the
new versioning rule (every build gets a new version number), on
`main` @ `d1c61f2`;
reference-corpus closure cycle: **Wave 4 complete** — all twelve W4 lanes
(WP-43/44/45/46p1/46p2/47/48/49/50/51/52/53/54/55/56/57 + WP-58 UI)
merged into `main` @ `0a38213`, cases 26 + 27 + 31 + 28 + 29 + 30
pinned as the 25th–30th corpus tables, 7475/7475 action-weighted over
6143 expected actions; historical plan
`plans/archive/reference-closure-continuation.md`). This is the binding result list:
confirmed state, measured numbers, and the prioritized open work. The
active plan lives in
[`plans/reference-table-100-roadmap.md`](../plans/reference-table-100-roadmap.md);
code/build boundaries in
[`native-runtime.md`](native-runtime.md) and
[`native-verification.md`](native-verification.md).

## 1. Goal and acceptance contract

- **Feature-matrix goal: 100% coverage of the in-scope 0.9 feature set
  (AP-11 excluded) — REACHED 2026-10-10 and closed, extended by WP-14 on
  2026-10-11, extended by WP-27/32/33/34 (W2-A) on 2026-10-14, extended
  by WP-30/36 (W2-C) on 2026-10-15 and by WP-28/29/31/35 (W2-B) on
  2026-10-16, extended by WP-39/40 (W3 batch 1), WP-38 (W3 batch 2),
  WP-41 (W3 batch 3) and WP-37 (W3 batch 4) on 2026-10-18, and by
  WP-43/44/45/47/48/51/52/55/56 (Wave 4 batches 1–3) on
  2026-10-19 and by WP-46 part 2, WP-49/50, WP-53/54, WP-57 +
  WP-58 (Wave 4 batch 4) on 2026-10-20.**
  42/42
  in-scope features covered (39 gap classes + 3
  gates); 100% feature-weighted; 7475/7475
  action-weighted over the pinned 6143-action corpus (30
  tables, run `w4b4-case30-20261020081722Z`). The 2026-10-19 state
  (7446/7446 over the 6119-action corpus, 27 tables, run
  `w4-case31-20261019061339`), the 2026-10-18 state
  (7426/7426 over the 6100-action corpus, 24 tables, run
  `w3e-case24-20261018051230`), the 2026-10-18 state (7416/7416 over
  the 6092-action corpus, 23 tables, run
  `w3d-case22-20261018040510`), the 2026-10-18 state (7413/7413 over
  the 6088-action corpus, 22 tables, run
  `w3b-case21-20261018023823Z`), the 2026-10-18 state (7411/7411 over
  the 6083-action corpus, 21 tables, run
  `w3-case23-20261018012531Z`), the 2026-10-16 state (7408/7408 over
  the 6080-action corpus, 20 tables, run
  `w2b-case18-20261016142912Z`), the 2026-10-15 state (7387/7387 over
  the 6062-action corpus, 19 tables, run
  `w2c-case15p2b-20261015144326Z`), the 2026-10-14 state (7381/7381 over
  the 6057-action corpus, 19 tables, run
  `w2a-case17-20261014112532Z`), the 2026-10-14
  state (7376/7376 over the 6047-action corpus, 18 tables, run
  `w1a-case15-20261014011543Z`), the 2026-10-14 state (7371/7371 over
  the 6031-action corpus, 17 tables, run
  `w1a-case16-20261014003107Z`), the 2026-10-13 state (7369/7369 over
  the 6025-action corpus, 16 tables, run
  `w1e-case20-20261013234642Z`), the 2026-10-13 state (7365/7365 over
  the 6019-action corpus, 15 tables, run
  `w1d-case19-20261013192913Z`), the 2026-10-11 state (7361/7361 over
  the 6011-action corpus, 14 tables, run
  `wp14-staged-20261011T093320Z`) and the 2026-10-10 39/39 over the 5967
  action corpus are superseded; the earlier 90% hurdle is subsumed.
- **Gates 1–3 are closed with real, tested evidence:**
  1. `gate:1` per-table completeness for all 30 pinned tables (Forms, Lua
     lifecycle, Custom Types, Assets) —
     `tests/test_native_table_completeness.py`.
  2. `gate:2` Source-to-Frozen parity of the 0.9 feature set —
     `tests/test_native_source_frozen_parity.py`, plus the binary
     CLI/GUI adapter for the static IL2CPP parser
     (`src/ct2trainer/native/il2cpp_static_probe.py`; frozen launcher
     flags `--il2cpp-static-pe/--il2cpp-static-metadata/--il2cpp-static-report`;
     source CLI `ct2trainer native il2cpp`;
     `tests/test_native_il2cpp_static_probe.py`).
  3. `gate:3` end-to-end reproducibility chain across all features with
     exact commands and pinned inputs —
     `tests/test_native_repro_chain.py` (denominator → feature matrix →
     AP-11 manifest, byte-identical per fixed run-id).
- **AP-11 (observed real-game effect for all 6143 pinned actions)
  remains a separate end goal** — 0 confirmed so far — and is excluded
  from the 100% feature metric.
- **Final product acceptance** is separate on Windows (clean PC/VM, no
  CE/Python) and on a real Steam Deck under Proton with touch operation.
  `runtime_unverified` stays set until both pass.

## 2. Confirmed state (0.9.0-rc2 + WP-14..58 + 0.16 field-fix re-cut 2 + 0.16.1/0.16.2/0.16.3/0.16.4 field fixes + RT-4.1 + RT-3 + RT-4.4 + RT-4.6 + RT-4.5 + RT-4.3 + RT-5 inventory + RT-5 items A/C/C2/D + 0.19 field fixes + 0.20/0.20.1 branding icons + RT-5 items B/E (RT-5 complete) + 0.21 Master Trainer, 2026-10-31 + 0.22 FO4 re-arm field-fix cycle, 2026-11-01 + 0.23 Master Trainer roadmap complete (MT-6/7/8/9), 2026-11-01 + 0.23 release build `native-20261101T145310Z-a160bae4`, 2026-11-01 + 0.24 trainer tick sounds, 2026-11-01 + 0.25 Master Trainer user control (MT-10/11/12), 2026-11-02 + 0.26 Master Trainer waiting-view usability (MT-13/14/15) + live-target takeover field fix, 2026-11-03 + 0.26 release build `native-20261103T112811Z-59a6b3d5`, 2026-11-03 + 0.27 Master Trainer waiting-view settings + process groups (MT-16/17), 2026-11-03 + 0.27 release build `native-20261103T145543Z-b29b3688`, 2026-11-03 + 0.28 Master Trainer pinned/favorite tables (MT-18), 2026-11-03 + 0.28 release build `native-20261103T161621Z-ea8fde2f`, 2026-11-03 + 0.29 Master Trainer UI/UX revamp (MT-19/20), 2026-11-04 + 0.29 release build `native-20261104T094808Z-50af0517`, 2026-11-04 + 0.30 Master Trainer table details + load-gate preview (MT-22), 2026-11-04 + 0.30 release build `native-20261104T131114Z-11522f68`, 2026-11-04)

| Item | Value |
| --- | --- |
| Repository baseline | `main` @ `b6c48cc` "initial 0.9 version" (self-contained clean-room tree) |
| Version | `0.30` (root `VERSION` file - the 0.30 content set on `main`: Master Trainer table details + live load-gate preview MT-22 2026-11-04, root-direct on `main` - the waiting-view row context menu offers "Table details" first (the read-only Toplevel with the indexed facts for the table - path, folder, size, modified, bound processes, index status, pin, last used, running PIDs, content sha - plus the on-demand `gate_table_for_load` re-check: the same pass MT-9 runs at load time, named refusal code + displayable detail; the pure `table_details.py` row builder; single window, lift on second open, closed on trainer entry; the only I/O is the bounded gate re-check under the load limit); the deferred MT-21 multi-column trainer grid, the entry-count / blocked-count columns and the per-table status / color-coding are documented as unchanged candidates; +16 tests; full main suite 4,386 OK / 30 expected skips; catalog zero delta `blocked-catalog-030-details`; previously `0.29` (the 0.29 content set on `main`: Master Trainer UI/UX revamp MT-19/20 2026-11-04, root-direct on `main` - MT-19 trainer-focus mode (the whole waiting view lives in one container frame `MasterWindow._waiting_frame` destroyed on trainer entry - the trainer row grid owns the full window, rebuilt whole on the way back; the trainer-constructor failure path rebuilds the waiting view before failing the load so the waiting loop and its loop guard stay consistent), MT-20 discoverability (the module function `ui_flow_text()` - the plain-language UI-flow document, the same content as the reviewable `master_trainer/UI.md` in the package, shipped in the source ZIP; the read-only "UI flow" header button - single Toplevel, lift on second click, closed on trainer entry; F5 re-scan from anywhere in the waiting view, guarded no-op in trainer mode; the initial table-list focus so arrow keys / Enter work immediately; the "Retry load" re-arm moved into the status bar); the deferred multi-column trainer grid is documented as candidate MT-21, separate cycle (the single-column canvas grid is the validated touch-first design; `ui_rows.py` + `ui_layout.py` are pure, exhaustively tested and shared with the standalone trainer); +13 tests; full main suite 4,370 OK / 30 expected skips; catalog zero delta `blocked-catalog-029-trainer-focus`; previously `0.28` (the 0.28 content set on `main`: Master Trainer pinned/favorite tables MT-18 2026-11-03, root-direct on `main` - `master-settings.json` schema 4 -> 5 (`pinned_tables` - relative table paths, most recent pin first, capped at `PINNED_TABLES_LIMIT` = 25; schema-4 documents promote on load with `pinned_tables=[]`, a schema-4 document carrying the field refused as an unknown field), the pure `table_filter.pin_tables` reshaping + the row context menu "Pin to top" / "Unpin" toggle + the top float in the list view and per process group + the detail-column pin marker (the first column stays the bare row identity); +15 tests; full main suite 4,357 OK / 30 expected skips; catalog zero delta `blocked-catalog-028-pin`; previously `0.27` (the 0.27 content set on `main`: Master Trainer waiting-view settings persistence MT-16 + process-grouped waiting view MT-17 2026-11-03, root-direct on `main` - MT-16 `master-settings.json` schema 3 -> 4 (`view_filter` at most 200 characters, "" = no filter; `view_sort`; `view_mode`; schema-1/2/3 documents promote on load, a schema-3 document carrying a view_* field refused as an unknown field; the format-level constants mirror `table_filter`), `MasterApp.set_view_settings` validates (named `ValueError`s) + re-persists immediately, the window restores all three at construction and every UI change re-persists; MT-17 the pure `group_tables_by_process` reshaping + the "View: list/process" cycle button + display-only group rows (`_is_table_row` gates all load points); +22 tests; full main suite 4,342 OK / 30 expected skips; catalog zero delta `blocked-catalog-027-view`; previously `0.26` (the 0.26 content set on `main`: Master Trainer waiting-view usability MT-13/14/15 2026-11-03, root-direct on `main` - MT-13 search/filter/sort (the new pure `table_filter.py` layer; casefolded substring over the table name AND any bound process name; name/process/status sort; session-only state), MT-14 keyboard flow (double-click/Return/KP_Enter load through the MT-10 path, "/" focuses the filter, Esc clears it), MT-15 recent tables (`master-settings.json` schema 3: `recent_tables` capped at ten, UTC timestamps, schema-1/2 promotion) + Size/Modified/Last-used columns + the "Recent: <path>" one-click load button; plus the live-target takeover field fix (owner proven dead + only target-side identities unproven -> user-confirmed attach to the still-running game; state archived byte-for-byte; wishes re-applied; code on `main` at `3ffa8fa`); +61 tests; full main suite 4,320 OK / 30 expected skips; catalog zero delta `blocked-catalog-026-master-ui`; previously `0.25` (the 0.25 content set on `main`: Master Trainer user control MT-10/11/12 2026-11-02, root-direct on `main` - MT-10 explicit table load (waiting-view "Load table" button + per-row "Load this table"; loads while the bound process is not running yet; `last_table` persisted in `master-settings.json` schema 2), MT-11 process picker + persisted attach mode (`process_picker.py` pure decision layer; "auto" smallest-PID default vs "ask" picker for every attach; schema-2 promotion), MT-12 detach / user attach (engine `pause_attach`/`resume_attach`/`attach_paused`, gated poll attach branch, "Detach"/"Attach" header button in Master mode only, standalone header byte-identical); online feature evaluation in `master_trainer/ROADMAP.md` (MT-10/11/12 adopted; global hotkeys / auto-update / concurrent multi-table sessions deliberately deferred); Tcl test-harness hardening (test-only `tests/native_tk_teardown.py`); in-build reliability fix (state-home isolation in the `run_master` cancel test + explicit-master Tk variables in `master_ui.py`, first in-build run `native-20261102T181843Z-ddfb63f0` exposed the dependence); +66 tests; full main suite 4,259 OK / 30 expected skips; catalog zero delta `blocked-catalog-025-master-ui`; previously `0.24` - the 0.24 content set on `main`: trainer tick sounds 2026-11-01, branch `native-0.24-trainer-sounds` - clean-room in-code tick synthesis (on/off/attach), `ui.py` rewired (row switch + group heading toggle + attach-success transition in `TrainerWindow.poll()`), `engine.py` `pop_hotkey_ui_toggles()` surfaces confirmed hotkey activation toggles, +21 tests (`tests/test_native_trainer_sounds.py`; supersedes `tests/test_native_ui_tone.py`, 4 tests, removed); full main suite 4,193 OK / 30 expected skips; catalog zero delta `blocked-catalog-024-sounds`; previously `0.23` - full Master Trainer roadmap 2026-11-01, branch `native-0.23-master-roadmap` merged `main` @ `b2d0344` + MT-9 load-gate branch `native-0.23-load-gate` merged @ `98a9226` + same-day field fixes (placeholder-heading `28c9b57`, SC2 hotkey-bridge 0.22.1 lane merge `4e9b95b`) - MT-6 per-table settings sidecar (content-sha keyed, restore-on-load / save-on-close) + MT-7 documented SteamOS/CheatDeck target route (named fail-closed non-Windows attach refusals, NOT a Linux attach backend) + MT-8 frozen `CT2Trainer-Master.exe` in every build + MT-9 load-time table compatibility & size gate + waiting-view observability + ask-on-first-start table-folder parameter, +115 tests; full main suite 4,176 OK / 30 expected skips; catalog zero delta `blocked-catalog-023-field-fixes` (all three 0.23 remeasures); the 0.23 build `native-20261101T145310Z-a160bae4` was cut from this content set (build record below); previously `0.22` - FO4 field-fix cycle 2026-11-01, branch `native-0.21-fo4-rearm` merged `main` @ `a12a0b6` - bounded automatic re-arm of ScanMiss enable failures (30 s x 10 attempts) + manual Try again / Re-attach actions, +17 tests; full main suite 4,061 OK / 30 expected skips; catalog zero delta `blocked-catalog-022-rearm`; the 0.22 build `native-20261101T075049Z-f32c112d` was cut from this
content set (build record below); previously `0.21` - RT-5 complete (items B + E) plus the 0.21 Master Trainer feature release (branch `native-0.20-master-trainer`, merged `main` @ `322ae22`); the 0.21 build was cut from `main` @ `9a725a8` as run `native-20261031T211046Z-14707e12` (in-build suite 4,044 OK / 30 expected skips, fully green at the canonical path); previously `0.20.1`, 2026-10-31, was the latest verified build; 0.9.0-rc2 was the last user-tested release, 0.16 user-tested 2026-10-20 with the WP-58 startup crash, fix in the re-cut; 0.16.1/0.16.2/0.16.3 field-tested 2026-10-21/22/23, 0.16.4 crash-observability field fix 2026-10-23/24; 0.17 released 2026-10-27, 0.18 released 2026-10-28, 0.19 field-fix release 2026-10-30 - Sinking City 2 hotkey-bridge AV + value-read observability, South of Midnight staged-options support; 0.20 branding icons 2026-10-30 - user-provided icon sets for the tool EXE and the generated trainers, 0.20.1 release-content re-cut 2026-10-31 - corrected 0.20 changelog suite line, cited `blocked-catalog-020-icons` remeasure) |
| Test suite | **4386 OK / 30 expected skips, 0 failures** (full main suite on `main` (0.30 content set), canonical path, 2026-11-04 - fully green, incl. the 3 path-dependent baseline-reproducibility tests; 4,370 from the 0.29 content + 16 new MT-22 tests (all in `tests/test_native_master_ui_mt22.py`); in-build suite on the 0.30 build run `native-20261104T131114Z-11522f68` identical at 4,386/30; previously **4370 OK / 30 expected skips, 0 failures** (full main suite on `main` (0.29 content set), canonical path, 2026-11-04 - fully green, incl. the 3 path-dependent baseline-reproducibility tests; 4,357 from the 0.28 content + 13 new MT-19/20 tests (all in `tests/test_native_master_ui_mt19.py`); in-build suite on the 0.29 build run `native-20261104T094808Z-50af0517` identical at 4,370/30; previously **4357 OK / 30 expected skips, 0 failures** (full main suite on `main` (0.28 content set), canonical path, 2026-11-03 - fully green, incl. the 3 path-dependent baseline-reproducibility tests; 4,342 from the 0.27 content + 15 new MT-18 tests (4 schema-5 state + 4 pure pin + 7 MT-18 UI); in-build suite on the 0.28 build run `native-20261103T161621Z-ea8fde2f` identical at 4,357/30; previously **4342 OK / 30 expected skips, 0 failures** (full main suite on `main` (0.27 content set), canonical path, 2026-11-03 - fully green, incl. the 3 path-dependent baseline-reproducibility tests; 4,320 from the 0.26 content + 22 new MT-16/17 tests (4 schema-4 state + 8 pure process-grouping + 10 MT-16/17 UI); in-build suite on the 0.27 build run `native-20261103T145543Z-b29b3688` identical at 4,342/30; previously **4320 OK / 30 expected skips, 0 failures** (full main suite on `main` (0.26 content set), canonical path, 2026-11-03 - fully green, incl. the 3 path-dependent baseline-reproducibility tests; 4,278 from the live-target takeover content + 42 new MT-13/14/15 tests (17 pure filter/sort + 13 recent/state + 12 MT-13/14/15 UI); previously **4259 OK / 30 expected skips, 0 failures** (full main suite on `main` (0.25 content set), canonical path, 2026-11-02 - fully green, incl. the 3 path-dependent baseline-reproducibility tests; 4,193 from the 0.24 content + 66 new MT-10/11/12 + reliability tests (16 process picker + 13 explicit load + 5 attach pause + 24 master UI MT-12 + 7 schema-2 master state + 1 state-home isolation); previously **4193 OK / 30 expected skips, 0 failures** (full main suite on `main` (0.24 content set), canonical path, 2026-11-01 - fully green, incl. the 3 path-dependent baseline-reproducibility tests; 4,176 from the 0.23 content - 4 removed `test_native_ui_tone.py` tests + 21 new `test_native_trainer_sounds.py` tests; previously **4176 OK / 30 expected skips, 0 failures** (full main suite on `main` @ `6e3ec98`, canonical path, 2026-11-01 - fully green, incl. the 3 path-dependent baseline-reproducibility tests; in-build suite on the 0.23 build run `native-20261101T145310Z-a160bae4` identical at 4,176/30; 4,133 after the 0.23 roadmap content + 22 MT-9 load-gate tests (16 gate + 2 orchestrator + 4 UI) + 10 placeholder-heading + 11 SC2 hotkey-bridge field-fix tests; previously **4133 OK / 30 expected skips, 0 failures** (full main suite on `main` @ `b2d0344`, canonical path, 2026-11-01 - fully green, incl. the 3 path-dependent baseline-reproducibility tests; 4,061 from the 0.22 build + 72 new master-trainer tests: 8 frozen entry + 17 settings sidecar + 13 SteamOS route + 15 master state + 13 master UI + 6 orchestrator tick-running; previously **4061 OK / 30 expected skips, 0 failures** (in-build suite on the 0.22 build run `native-20261101T075049Z-f32c112d` from `main` @ `2b24a1c`, canonical path, 2026-11-01 - fully green, incl. the 3 path-dependent baseline-reproducibility tests; identical dev suite on `main` @ `a12a0b6` after the 0.22 FO4 re-arm merge, 2026-11-01; previously **4044 OK / 30 expected skips, 0 failures** (in-build suite on the 0.21 content set, build run `native-20261031T211046Z-14707e12` from `main` @ `9a725a8`, canonical path, 2026-10-31 - fully green, incl. the 3 path-dependent baseline-reproducibility tests; previously **4011 OK / 30 expected skips, 0 non-environmental failures** (full dev suite on branch `native-0.20-master-trainer` after the 0.21 Master Trainer work + the RT-5 B/E and ce-analysis merges, 4,044 run; the only 3 failures are the known worktree path-dependent baseline-reproducibility tests, which pass at the canonical build path; previously **3902 OK / 26 expected skips, 0 failures** (full local dev suite on `main` after the RT-5 item B/E merges - CheatCodes code-patch plan path (`tests/test_native_rt5_code_patch.py` +26, catalog `blocked-catalog-020-rt5-be`: 117,634 -> 117,809 total, 116,581 -> 116,756 supported (+175), zero newly blocked, zero reason changes) and the messageDialog safe logged no-op (`tests/test_native_rt5_message_dialog.py` +22, zero catalog delta `blocked-catalog-rt5e-iteme`); RT-5 now complete, verified 2026-10-31 at the canonical path with CT2TRAINER_NASM set; previously 3854 OK / 26 expected skips, 0 failures (in-build suite on `main` @ `080128c` after the 0.20.1 release-content re-cut - branding-icon release with the corrected 0.20 changelog suite line, verified 2026-10-31 in build run `native-20261031T104114Z-d64ae4c2` at the canonical path; the 0.20 content was already verified at the identical 3854/26 in-build on 2026-10-30, run `native-20261030T184820Z-b9d6dc07`, +4 tests from `tests/test_native_icons.py`; previously 3850 OK / 26 expected skips, 0 failures (in-build suite on `main` after the 0.19 field-fix cycle - hotkey-bridge AV fix, value-read observability, describe CLI, staged-options support (South of Midnight), +24 tests, verified 2026-10-30 at the canonical path with CT2TRAINER_NASM set; previously 3826 OK / 25 expected skips, 0 failures (full local dev suite on `main` after the RT-5 item D onOpenProcess/onTableLoad callback dispatch merge - CE-sequence table-scope dispatch after a clean table-Lua bootstrap (onOpenProcess with the attached target PID, onTableLoad with the Lua literal false - documented bounded deviation: no before-load phase), pcall-wrapped dispatch chunks with literal argument injection, 'absent'/'ok'/'error: <msg>' -> no event / table-callback / table-callback-error, throwing-callback containment with plan byte-identity, idempotent per confirmed attach, re-attach re-fire, `tests/test_native_rt5_table_callbacks.py` +9, verified 2026-10-29 at the canonical path with CT2TRAINER_NASM set; previously 3817 OK / 25 expected skips, 0 failures (full local dev suite on `main` after the RT-5 item C2 dynamic addresslist records + custom AA directives merge - createMemoryRecord session journal, CE MemoryRecord runtime surface, journal + plan OnActivate/OnDeactivate callbacks, getCEVersion number 7.5 pin, registerAutoAssemblerCommand custom directive expansion, `tests/test_native_rt5_dynamic_records.py` +27, verified 2026-10-29 at the canonical path with CT2TRAINER_NASM set; previously 3790 OK / 25 expected skips, 0 failures (full local dev suite on `main` after the RT-5 item C bounded process-info Lua API family merge - 11 APIs under the clean-room single-target model (getProcessIDFromProcessName, getProcessList, getAutoAttachList, getOpenedProcessID, getSettings, integerToUserData, targetIs64Bit, enumModules, disassemble, stringlist_add, getCEVersion), `tests/test_native_rt5_process_info.py` +23, verified 2026-10-28 at the canonical path with CT2TRAINER_NASM set; previously 3767 OK / 25 expected skips, 0 failures (full local dev suite on `main` after the 0.18 trainer UI row-details window - "Row details" leads the row context menu, one read-only window with the raw script source + plain-language assessment + concrete actions per entry, new pure builders `entry_actions` / `row_details` / `lua_apis_used` in `ui_script_view.py`, `tests/test_native_ui_row_details.py` +22, verified 2026-10-28 at the canonical path with CT2TRAINER_NASM set; previously 3692 OK / 25 expected skips, 0 failures (full local dev suite on `main` after the RT-4.2 runtime provider model merge - keep-first duplicate-provider scope fallback, mixed-dialect `unregistersymbol` release evidence, bounded API-export registry with link-time resolution; `tests/test_native_rt42_runtime_provider.py` +21 plus the R7 pin migration in `tests/test_native_undefined_provider_report.py`, verified 2026-10-27 at the canonical path with CT2TRAINER_NASM set; the 0.17 in-build suite is identical: 3692/25; previously 3670 OK / 25 expected skips, 0 failures (full local dev suite on `main` after the RT-5 item F no-effect register ratification - tests only, `tests/test_native_rt5_no_effect_register.py` +22, verified 2026-10-26; previously 3479 OK / 25 expected skips, 0 failures (full local dev suite on `main` after the RT-4.4 value-semantics merge - O6/O8 dropdown width truncation + expression choices per the CE SetValue conclusions, O7 ShowAsHex strings staged as byte_array profiles, O26 empty/placeholder-only read-only dropdowns staged as display-only views, O11 custom-type gate kept by design (`tests/test_native_value_semantics.py` +18 plus pin updates in dropdown/value/compiler/engine modules), verified 2026-10-23 at the canonical path with CT2TRAINER_NASM set; previously 3450 OK / 25 expected skips, 0 failures (full local dev suite on `main` after the RT-3 legacy-binary CT loader merge — clean-room parser `src/ct2trainer/legacy_ct.py`, +28 `tests/test_native_legacy_ct.py`, updated legacy pins in `tests/test_native_table_robustness.py`, verified 2026-10-23 at the canonical path with CT2TRAINER_NASM set; previously 3421 OK / 25 expected skips, 0 failures (full local dev suite on `main` after the 0.16.3 field fix - hook-journal `value_data_ranges` accepted by the recovery assessment + module-snapshot transient retry with backoff (`tests/test_native_architecture.py` +4, `tests/test_native_recovery.py` +2), verified 2026-10-23 at the canonical path with CT2TRAINER_NASM set; previously 3415 OK / 25 expected skips, 0 failures (full local dev suite on `main` after the RT-4.1 symbol provider fidelity merge — keep-first duplicate-provider policy, `label()` duplicate-name tolerance, wildcard-cleanup scoping (nine focused modules, 167 tests, incl. `tests/test_native_provider_selection_dedupe.py`), verified 2026-10-22 at the canonical path with CT2TRAINER_NASM set; previously 3414 OK / 25 expected skips, 0 failures (full local dev suite on `main` after the 0.16.2 field fix — WP-57 hook journal `captured_placeholders` accepted by the recovery assessment (`tests/test_native_recovery.py`, +2 tests), verified 2026-10-22 at the canonical path with CT2TRAINER_NASM set; previously 3412 OK / 25 expected skips, 0 failures (full local dev suite on `main` after the 0.16.1 SC2 table-load warning fix — table-version reference 45 → 46 + accurate `{$LUA}`/external-action warnings (`tests/test_native_sc2_table_warnings.py`, version assertion in `tests/test_native_compiler.py`), verified 2026-10-21 at the canonical path with CT2TRAINER_NASM set; previously 3405 on `main` after the 0.16 field-fix round 2 — state-lock self-repair and reliable restart (`tests/test_native_stale_lock_selfheal.py`, updated variant-close assertion in `tests/test_native_engine.py`), verified 2026-10-21 at the canonical path with CT2TRAINER_NASM set; previously 3398 on `main` after the 0.16 field-fix cycle — WP-58 UI startup crash fix + Sinking City 2 runtime chain evidence (`tests/test_native_ui_button.py`, `tests/test_native_sc2_attach_chain.py`), verified 2026-10-20 at the canonical path with CT2TRAINER_NASM set; previously 3393 on `main` after the W4 B4 merges and the case-28/29/30 pins, verified 2026-10-20 at the canonical path; previously 3233 on `main` after the W4 cycle merge and the case-26/27/31 pins, verified 2026-10-19 at the canonical path; previously 3057 on `native-0.15` after the W3 batch 1 + batch 2 + batch 3 + batch 4 merges (WP-39/40/38/41/37) and the case-23 + case-21 + case-22 + case-24 pins, verified 2026-10-18; previously 3046 after the W3 batch 3 merge (WP-41) and the case-22 pin; previously 3001 after the W3 batch 1 + batch 2 merges (WP-39/40/38) and the case-23 + case-21 pins, verified 2026-10-18 at the canonical path; previously 2943 after the 0.15 prefix-cut field fix at `d15268a`, 2026-10-17; previously 2932 on `native-0.14` after the per-wish restore isolation and program-scan debug logging, verified 2026-10-17 at the canonical path; previously 2927 on `native-0.13` after the optional debug-logging feature incl. attach-failure dedupe and the module-snapshot fallback, verified 2026-10-16; previously 2925 after the debug-logging feature; previously 2910 after the W2-C + W2-B merges and the case-15 part 2 + case-18 pins; previously 2840 after the W2-A merge and the case-20 + case-16 + case-17 + case-15 pins, verified 2026-10-14; previously 2805 after the W1-A + W1-E merges and the case-20 + case-16 + case-15 pins; previously 2769 after the W1-D + W1-C + W1-B integration; previously 2710 after the WP-18 merge `9a76eb8`; previously 2698 after the WP-17 merge `557b2ac`; previously 2688 after the WP-15 merge `d3316aa`; previously 2679 on `native-l5-19` after the WP-16 merge `38a830d`; previously 2671 on `native-0.9-staged` after the WP-14 gate-test merge `54b172e`); in-build suite 2932/25 passed (0.14 build `native-20261017T115850Z-1ebb48b7`); previously 2927/25 (0.13 build `native-20261016T190005Z-b3139b30`); previously 2925/25 (superseded 0.13 build `native-20261016T181516Z-b8ae88de`); previously 2910/25 (0.12 build `native-20261016T163910Z-d047f2d2`); previously 2710/25 (0.11 build `native-20261012T092729Z-2d8aaf12`); previously 2698/25 (0.11 build `native-20261011T182033Z-f3317337`); previously 2671/25 (0.10 build `native-20261011T121914Z-bfc5fc11`) |
| Feature matrix | **42/42 covered** (100% feature-weighted, 7475/7475 action-weighted; run `w4b4-case30-20261020081722Z`; previously 7446/7446, run `w4-case31-20261019061339`; previously 7426/7426, run `w3e-case24-20261018051230`; previously 7416/7416, run `w3d-case22-20261018040510`; previously 7413/7413, run `w3b-case21-20261018023823Z`; previously 7411/7411, run `w3-case23-20261018012531Z`) — `gap_inventory/feature-coverage.json` |
| AP-11 manifest | 30 tables, 6143 expected actions, 0 confirmed, all consistency gates `all_ok` (run `w4b4-case30-20261020081722Z`; previously 27 tables / 6119 actions, previously 24 tables / 6100 actions, previously 23 tables / 6092 actions) — `gap_inventory/ap11-campaign.json` |
| Latest verified build | `native-20261104T131114Z-11522f68` (0.30) via `scripts/Build-Native.ps1` from `main` @ `2fbca94` (2026-11-04): in-build suite 4,386 OK / 30 expected skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per gate; both ZIPs (`CT2Trainer-0.30-source.zip` sha256 `091b379c132e277c19f519705dcccc4c0817e8e7e614e5baf2f14bbe3fe414a3`, 14,387,690 bytes, `CT2Trainer-0.30-windows-portable.zip` sha256 `f4476bb08e3e65e6db9cd35bfe7a72408a555b8525bd6a10f8b794f943083d54`, 49,669,933 bytes); the portable ZIP carries the frozen `CT2Trainer-Master.exe` (sha256 `9d0a525a`, 16,940,058 bytes) next to the converter, the payload inventory and the source ZIP. 0.30 ships the Master Trainer table details + live load-gate preview (MT-22; see the 0.30 ledger section below). Superseded 0.29 build: `native-20261104T094808Z-50af0517` (0.29) via `scripts/Build-Native.ps1` from `main` @ `de3e4ff` (2026-11-04): in-build suite 4,370 OK / 30 expected skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per gate; both ZIPs (`CT2Trainer-0.29-source.zip` sha256 `2f5ce6e446f8d9885cd653580b5e194a2a0fc524eba7b5f684fe1f1a0e1da3d4`, 14,378,934 bytes, `CT2Trainer-0.29-windows-portable.zip` sha256 `98c63c368bc2cccd68335e9db94a3b897abbbb815730c97912e3068805fad226`, 49,667,528 bytes); the portable ZIP carries the frozen `CT2Trainer-Master.exe` (sha256 `88e6ee99`, 16,937,063 bytes) next to the converter, the payload inventory and the source ZIP. 0.29 ships the Master Trainer UI/UX revamp (MT-19 trainer-focus mode + MT-20 discoverability; see the 0.29 ledger section below). Superseded 0.28 build: `native-20261103T161621Z-ea8fde2f` (0.28) via `scripts/Build-Native.ps1` from `main` @ `d7f4cf0` (2026-11-03): in-build suite 4,357 OK / 30 expected skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per gate; both ZIPs (`CT2Trainer-0.28-source.zip` sha256 `13f4b2222a83f9e4588d388b4120beaf8018a091a05364029ae2a950c0dabb1a`, 14,363,765 bytes, `CT2Trainer-0.28-windows-portable.zip` sha256 `d656835a69ece75ff6adaa5ce766385327fb9ec08d89837ad772425dafe91ce3`, 49,658,473 bytes); the portable ZIP carries the frozen `CT2Trainer-Master.exe` (sha256 `c12dcea5`, 16,929,732 bytes) next to the converter, the payload inventory and the source ZIP. 0.28 ships the Master Trainer pinned/favorite tables MT-18 (`master-settings.json` schema 4 -> 5: `pinned_tables`; see the 0.28 ledger section below). Superseded 0.27 build: `native-20261103T145543Z-b29b3688` (0.27) via `scripts/Build-Native.ps1` from `main` @ `8aa0815` (2026-11-03): in-build suite 4,342 OK / 30 expected skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per gate; both ZIPs (`CT2Trainer-0.27-source.zip` sha256 `264b42d6c42dac1bb434c1d0591e82ac0bec69e61e1a1c75047c6aa58126f40e`, 14,357,294 bytes, `CT2Trainer-0.27-windows-portable.zip` sha256 `bfcf2abc885122dfa8653fcfd0046323e7112f59c0850958688e36e014ebc135`, 49,654,613 bytes); the portable ZIP carries the frozen `CT2Trainer-Master.exe` (sha256 `9762c8bd`, 16,929,639 bytes) next to the converter, the payload inventory and the source ZIP. 0.27 ships the Master Trainer waiting-view settings persistence MT-16 (`master-settings.json` schema 3 -> 4: `view_filter` / `view_sort` / `view_mode`) and the process-grouped waiting view MT-17 (see the 0.27 ledger section below). Superseded 0.26 build: `native-20261103T112811Z-59a6b3d5` (0.26) via `scripts/Build-Native.ps1` from `main` @ `c114ec2` (2026-11-03): in-build suite 4,320 OK / 30 expected skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per gate; both ZIPs (`CT2Trainer-0.26-source.zip` sha256 `3d62f80cdfb95d8439d4a2f2150002976795faad313fa75d47aeb4fb92bb49bd`, 14,348,462 bytes, `CT2Trainer-0.26-windows-portable.zip` sha256 `49be1d286999ed175737edb073c5ab83533c40cccc7e636685a256a0b07004b3`, 49,653,968 bytes); the portable ZIP carries the frozen `CT2Trainer-Master.exe` (sha256 `895f937e`, 16,925,677 bytes) next to the converter, the payload inventory and the source ZIP. 0.26 ships the Master Trainer waiting-view usability MT-13/14/15 (search/filter/sort, keyboard load flow, rolling recent tables + Size/Modified/Last-used columns) and the live-target takeover field fix (see the 0.26 ledger section below). Superseded 0.25 build: `native-20261103T062439Z-f4c16be9` (0.25) via `scripts/Build-Native.ps1` from `main` @ `a861bfb` (2026-11-03): in-build suite 4,259 OK / 30 expected skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per gate; both ZIPs (`CT2Trainer-0.25-source.zip` sha256 `64f8c3082cff50687b1962234c17a82e2a2f0c19eb1112ece06a0a25132f35be`, 14,324,774 bytes, `CT2Trainer-0.25-windows-portable.zip` sha256 `774266f7e2c9dc69f4d8cfc963309b9907442ec6b5343ff629b9e30c04049653`, 49,633,196 bytes); the portable ZIP carries the frozen `CT2Trainer-Master.exe` (sha256 `8736f73e`, 16,912,561 bytes) next to the converter, the payload inventory and the source ZIP. 0.25 ships the Master Trainer user control MT-10/11/12 (explicit table load, process picker + persisted attach mode, detach/user attach), the online feature evaluation record, the Tcl test-harness hardening and the in-build reliability fix (see the 0.25 ledger section below). Superseded 0.24 build: `native-20261102T102029Z-fe358e35` (0.24) via `scripts/Build-Native.ps1` from `main` @ `a2777ed` (2026-11-02): in-build suite 4,193 OK / 30 expected skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per gate; both ZIPs (`CT2Trainer-0.24-source.zip` sha256 `dfdd8cfcca90a2789bf544d8f8de4e34941067feeb2b32ce8d550f98e5bc4eb6`, 14,298,696 bytes, `CT2Trainer-0.24-windows-portable.zip` sha256 `12262cf16e906c3811ade0a8c582b7a1057c834a3110aff004dfd13b3067e7ab`, 49,618,009 bytes); the portable ZIP carries the frozen `CT2Trainer-Master.exe` (sha256 `5f3a6640`, 16,896,995 bytes) next to the converter, the payload inventory and the source ZIP. 0.24 ships the trainer tick sounds (see the 0.24 ledger section below). Superseded 0.23 build: `native-20261101T145310Z-a160bae4` (0.23) via `scripts/Build-Native.ps1` from `main` @ `6e3ec98` (2026-11-01): both ZIPs (`CT2Trainer-0.23-source.zip` sha256 `3360cab0`, `CT2Trainer-0.23-windows-portable.zip` sha256 `eec023ba`), in-build suite 4176 OK / 30 expected skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per gate; the source ZIP carries the `master_trainer` subpackage incl. `table_gate.py`, the MT-9 test file, the placeholder-heading + SC2 hotkey-bridge field-fix test files and the final 0.23 changelog entry; the portable ZIP carries the frozen `CT2Trainer-Master.exe` (sha256 `e5822f68`, 16,895,048 bytes) next to the converter. 0.23 is the Master Trainer roadmap release incl. the MT-9 load gate + the same-day field fixes (see the 0.23 ledger sections below). Superseded 0.22 build: `native-20261101T075049Z-f32c112d` (0.22) via `scripts/Build-Native.ps1` from `main` @ `2b24a1c` (2026-11-01): both ZIPs (`CT2Trainer-0.22-source.zip` sha256 `c5db1b92`, `CT2Trainer-0.22-windows-portable.zip` sha256 `f89cd022`), in-build suite 4061 OK / 30 expected skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per gate; the source ZIP carries the re-arm tests (`tests/test_native_rearm.py`) and the 0.22 changelog entry; both ZIPs carry the changelog with the 0.22 + 0.21 + 0.20.1 + 0.20 entries. 0.22 is the FO4 field-fix cycle release (see the 0.22 field-cycle section below). Superseded 0.21 build: `native-20261031T211046Z-14707e12` (0.21) via `scripts/Build-Native.ps1` from `main` @ `9a725a8` (2026-10-31): both ZIPs (`CT2Trainer-0.21-source.zip` sha256 `9dacb409`, `CT2Trainer-0.21-windows-portable.zip` sha256 `0701d507`), in-build suite 4044 OK / 30 expected skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per gate; the source ZIP carries the `master_trainer` subpackage (code + in-package docs), all 4 master test files and the `Master_Trainer` icon assets; both ZIPs carry the changelog with the 0.21 + 0.20.1 + 0.20 + 0.19 entries. 0.21 is the RT-5-complete + Master Trainer feature release (see the 0.21 ledger sections below). Superseded 0.20.1 build: `native-20261031T104114Z-d64ae4c2` (0.20.1) via `scripts/Build-Native.ps1` from `main` @ `080128c` (2026-10-31): both ZIPs (`CT2Trainer-0.20.1-source.zip` sha256 `d6ced6ee`, `CT2Trainer-0.20.1-windows-portable.zip` sha256 `c8f022b1`), in-build suite 3854 OK / 26 expected skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per gate; both ZIPs carry the changelog with the 0.20.1 + 0.20 + 0.19 entries. 0.20.1 is the release-content re-cut of the 0.20 branding-icon release (only the 0.20 changelog suite line corrected to the verified in-build numbers + the `blocked-catalog-020-icons` remeasure cited; no code or asset changes). Superseded 0.20 build: `native-20261030T184820Z-b9d6dc07` (0.20) via `scripts/Build-Native.ps1` from `main` @ `6298803` (2026-10-30): both ZIPs (`CT2Trainer-0.20-source.zip` sha256 `9ca6dca6`, `CT2Trainer-0.20-windows-portable.zip` sha256 `bddaed80`), in-build suite 3854 OK / 26 expected skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per gate; both ZIPs carry the changelog with the 0.20 + 0.19 + 0.18 entries. 0.20 ships the user-provided branding icons (`CT2Trainer_Generator` set on the tool EXE - PyInstaller `--icon` + `window_icon_path("converter")`; `Standalone_Trainer` set embedded in the `CT2Trainer-Template` stub so every generated trainer carries it - `window_icon_path("trainer")`; 1024x1024 PNG masters committed, multi-size ICOs (16-256 px, 32 bpp) rebuilt by the rewritten `tools/create_icons.py`, `tests/test_native_icons.py` +4; the build source inputs carry the new icon hashes byte-identical to the committed assets, and PE icon-resource extraction confirms both frozen EXEs carry the new icons with the largest embedded blob byte-identical to the committed ICO's 256-px entry). Superseded 0.19 build: `native-20261030T121918Z-c72dbb38` (0.19) via `scripts/Build-Native.ps1` from `main` @ `fbe626f` (2026-10-30): both ZIPs (`CT2Trainer-0.19-source.zip` sha256 `3eaa6a98`, `CT2Trainer-0.19-windows-portable.zip` sha256 `a440051c`), in-build suite 3850 OK / 26 expected skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per gate; both ZIPs carry the changelog with the 0.19 + 0.18 + 0.17 entries. 0.19 ships the field-fix cycle (Sinking City 2: hotkey-bridge AV fix + value-read observability; `describe` CLI; South of Midnight: staged-options support - two-level cascade proof, staged-pending tap guard, moAlwaysHideChildren pass-through + row suppression; +24 tests) on top of the 0.18 content. Superseded 0.18 build: `native-20261028T131208Z-55922918` (0.18) via `scripts/Build-Native.ps1` from `main` @ `70c5a61` (2026-10-28): both ZIPs (`CT2Trainer-0.18-source.zip` sha256 `3d8612ed`, `CT2Trainer-0.18-windows-portable.zip` sha256 `9e4080e0`), in-build suite 3767 OK / 25 expected skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per gate; both ZIPs carry the changelog with the 0.18 + 0.17 + 0.16.4 + 0.16.3 + 0.16.2 + 0.16.1 + 0.16 + 0.15 + 0.14 entries. 0.18 ships the trainer UI row-details window (right-click / long-press on a row offers "Row details" leading the context menu - one read-only window with the raw script source, the plain-language assessment and the concrete actions per entry; new pure builders `entry_actions` / `row_details` / `lua_apis_used` in `ui_script_view.py`, `tests/test_native_ui_row_details.py` +22) on top of the 0.17 content. Superseded 0.17 build: `native-20261027T094839Z-ec6c6f55` (0.17) via `scripts/Build-Native.ps1` from `main` @ `ee41630` (2026-10-27): both ZIPs (`CT2Trainer-0.17-source.zip` sha256 `08af7d40`, `CT2Trainer-0.17-windows-portable.zip` sha256 `ee6ad2ec`), in-build suite 3692 OK / 25 expected skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per gate; both ZIPs carry the changelog with the 0.17 + 0.16.4 + 0.16.3 + 0.16.2 + 0.16.1 + 0.16 + 0.15 + 0.14 entries. 0.17 ships the RT-4.2 runtime provider model (last RT-4 package; catalog remeasure `blocked-catalog-rt42-main`: 1,351 -> 1,053 blocked of 117,634, 298 rows unblocked, zero newly blocked, 28 reason-only changes) plus the RT-4.3 address-expression & identifier-dialect merge, the RT-4.5 and RT-4.6 merges, the trainer UI Scripts view and row context menu, and the RT-5 item G / F gate ratifications on top of the 0.16.4 content. Superseded 0.16.4 build: `native-20261024T003853Z-a8cf04fc` (0.16.4) via `scripts/Build-Native.ps1` from `main` @ `988ff8e` (2026-10-24): both ZIPs (`CT2Trainer-0.16.4-source.zip` sha256 `87e1f448`, `CT2Trainer-0.16.4-windows-portable.zip` sha256 `ffa08832`), in-build suite 3479 OK / 25 expected skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per gate; both ZIPs carry the changelog with the 0.16.4 + 0.16.3 + 0.16.2 + 0.16.1 + 0.16 + 0.15 + 0.14 entries. 0.16.4 ships the Sinking City 2 trainer-crash-observability field fix (crash hooks + faulthandler sink into the opt-in debug log, fail-closed poll guard, `restore-entry-start` markers, `tests/test_native_sc2_crash_observability.py` +8) on top of the 0.16.3 content and the RT-4.4 value-semantics merge (catalog remeasure `blocked-catalog-rt44`: 1,858 -> 1,807 blocked of 117,634, zero newly blocked rows). Superseded 0.16.3 build: `native-20261023T065015Z-afbc3eba` (0.16.3) via `scripts/Build-Native.ps1` from `main` @ `6a5ba63` (2026-10-23): both ZIPs (`CT2Trainer-0.16.3-source.zip` sha256 `0b34c4f3`, `CT2Trainer-0.16.3-windows-portable.zip` sha256 `bb495a6f`), in-build suite 3421 OK / 25 expected skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per gate; both ZIPs carry the changelog with the 0.16.3 + 0.16.2 + 0.16.1 + 0.16 + 0.15 + 0.14 entries. 0.16.3 ships the Sinking City 2 activation field fix (recovery assessment accepts the hook-journal `value_data_ranges` allocation field; module-snapshot transient retry with correct Win32 codes, bounded exponential backoff, architecture-aware fallback flag; regression tests `tests/test_native_architecture.py` +4, `tests/test_native_recovery.py` +2) on top of the 0.16.2 content. Superseded 0.16.2 build: `native-20261022T160328Z-0423fb21` (0.16.2) via `scripts/Build-Native.ps1` from `main` @ `68eeb00` (2026-10-22): both ZIPs (`CT2Trainer-0.16.2-source.zip` sha256 `1e284d2a…`, `CT2Trainer-0.16.2-windows-portable.zip` sha256 `9c8ccc9e…`), in-build suite 3415 OK / 25 expected skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per gate; both ZIPs carry the changelog with the 0.16.2 + 0.16.1 + 0.16 + 0.15 + 0.14 entries. 0.16.2 ships the Sinking City 2 startup-block field fix (recovery assessment accepts the WP-57 hook-journal `captured_placeholders` field, regression tests `tests/test_native_recovery.py`) and RT-4.1 symbol provider fidelity (keep-first duplicate-provider policy, `label()` duplicate-name tolerance, wildcard-cleanup scoping; catalog remeasure 2,698 -> 1,858 blocked of 117,624, zero unexplained supported regressions) on top of the 0.16.1 content. Superseded 0.16.1 build: `native-20261021T161241Z-b0566a25` (0.16.1, first build under the new versioning rule, cut from `main` @ `d1c61f2`; in-build 3412/25, `ce_inputs: []`, user-tested, field finding: Sinking City 2 startup block). 0.16.1 ships the SC2 table-load warning fixes (table-version reference 45 → 46 field-verified; `{$LUA}` warning states the built-in Lua runtime path; external-action warning split per API — ShellExecute safe no-op, messageDialog review flag) on top of the 0.16 content. 0.16 ships the full Wave 4 feature set (WP-43…WP-57 + WP-58 UI) plus the post-release field fixes (WP-58 UI startup crash fix + Sinking City 2 activation-chain runtime evidence + state-lock self-repair and reliable restart) on top of the released 0.15 content. Superseded 0.16 runs: `native-20261021T141051Z-17d53c1d` (0.16, cut from `main` @ `e9f06fb` after the RT-1 rebaseline, in-build 3405/25, `ce_inputs: []`, superseded by the 0.16.1 cut before its evidence was recorded), `native-20261021T123801Z-8c5c4e1e` (0.16 field-fix re-cut 2, cut from `main` @ `108170b`, in-build 3405/25, user-tested, field finding: Sinking City 2 table-load warnings), `native-20261020T150115Z-c426fb92` (cut from `main` @ `7616edb`, in-build 3398/25, user-tested, field findings: one cheat = table/build mismatch, state-lock orphan after a blocked close) and `native-20261020T103508Z-0e3f9d90` (cut from `main` @ `809666a`, in-build 3393/25, user-tested, shipped with the WP-58 UI startup crash). Previous: `native-20261018T055505Z-39f20180` (0.15) via `scripts/Build-Native.ps1` from `main` @ `ed0b97b` (2026-10-18): both ZIPs (`CT2Trainer-0.15-source.zip` sha256 `5d5a85f6…`, `CT2Trainer-0.15-windows-portable.zip` sha256 `cfcc8e06…`), in-build suite 3057 OK / 25 expected skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per gate; both ZIPs carry the elaborated release READMEs and the changelog with the 0.15 + 0.14 + 0.13 entries. 0.15 ships the prefix-cut byte-patch validation (the 0.14-ext2 Great Circle field finding: Stealth Mode and No Reload use `db 90 E9` over a 6-byte conditional jump, now proven at link time and re-verified at stage time) plus the full Wave 3 feature set on top of the 0.14 content. Previous: `native-20261017T115850Z-1ebb48b7` (0.14, in-build 2932/25); `native-20261016T190005Z-b3139b30` (0.13, in-build 2927/25); `native-20261016T181516Z-b8ae88de` (0.13 pre module-snapshot fallback, in-build 2925/25); `native-20261016T163910Z-d047f2d2` (0.12, in-build 2910/25); `native-20261016T161905Z-e8ef67a0` (0.12, byte-identical re-cut); `native-20261016T154141Z-2de774ab` (0.12 pre release-docs); `native-20261012T092729Z-2d8aaf12` (0.11, in-build 2710/25); `native-20261011T121914Z-bfc5fc11` (0.10, in-build 2671/25); `native-20261010T172336Z-ffe35eb0` (rc2, in-build 2617/25, `api-prototypes.json` present in both EXE payload inventories, user-tested portable) |
| User-tested portable | run `native-20261010T165731Z-3d1da645`: converter run + generated trainer verified by the user on a machine without CE/Python |
| Reference-corpus assessment (2026-10-13) | 151 local-only reference tables: baseline 117,019 plan entries, 95,167 supported (incl. 46,987 staged), **21,852 blocked**, 4 whole-table compile errors (run `ref-assessment`); after W1-D (WP-25) + W1-C (WP-22/23): **21,851 of 117,255 blocked**, 3 whole-table compile errors — Octopath compiles (227 supported / 9 blocked, 24 duplicate-ID warnings), 20XX fully supported (10/10), SuperMeatBoy refused with a named legacy-binary error (catalog re-run 2026-10-13); after W1-B + W1-A + W1-E: **10,892 of 117,624 blocked**, 1 whole-table compile error (SuperMeatBoy legacy binary only; AtomicHeart `$process` closed by WP-19, Cyberpunk `@@` by WP-20) (catalog re-run 2026-10-14); after W2-A (WP-27/32/33/34): **9,962 of 117,624 blocked**, 1 whole-table compile error (SuperMeatBoy only; catalog re-run 2026-10-14, `blocked-catalog-w2a.json`; −930 blocked, 0 supported regressions, +197 previously masked records now surface the named missing-target reason); after W2-B + W2-C (WP-28/29/31/35 + WP-30/36): **7,577 of 117,624 blocked** (−2,385, 0 supported regressions; 1 whole-table compile error, SuperMeatBoy only; catalog re-run 2026-10-16, `blocked-catalog-w2final.json`); after W4 B1–B3 (WP-43/44, WP-46 part 1, WP-47/55, WP-45/56, WP-51/48, WP-52): **3,632 of 117,624 blocked** (−3,945, supported 113,992 incl. 58,018 staged; 1 whole-table compile error, SuperMeatBoy only; catalog re-run 2026-10-19, `blocked-catalog-w4final.json`); after W4 B4 (WP-46 part 2, WP-49/50, WP-53/54, WP-57, WP-58): **2,698 of 117,624 blocked** (−934, supported 114,926 incl. 58,950 staged; 1 whole-table compile error, SuperMeatBoy only; catalog re-run 2026-10-20, `blocked-catalog-w4b4.json`); after RT-4.1 (symbol provider fidelity, 2026-10-22): **1,858 of 117,624 blocked** (net −840: 842 unblocked, 2 explained Cyberpunk shared-global regressions; supported 115,766 incl. 59,642 staged; 1 whole-table compile error, SuperMeatBoy only; catalog re-run `blocked-catalog-rt41`); after RT-3 (legacy-binary CT loader, 2026-10-23): **1,858 of 117,634 blocked**, **151/151 tables load** (the last whole-table load error cleared; `SuperMeatBoy.CT` now compiles to 10 supported / 0 staged / 0 blocked records; the other 150 tables byte-identical per-table; supported 115,776 incl. 59,642 staged; catalog re-run `blocked-catalog-rt3`); after RT-4.4 (value semantics, 2026-10-23): **1,807 of 117,634 blocked** (net -51 vs `blocked-catalog-rt3`: O6/O7/O8/O26 value-semantics rows cleared, zero newly blocked, 8 rows reason-changed onto pre-existing symbol-provider blocks; supported 115,827 incl. 59,683 staged; 151/151 load; catalog re-run `blocked-catalog-rt44`); consolidated assessment `documentation/reference-gap-assessment.md`, closure plan `plans/archive/reference-closure-continuation.md` (WP-19…WP-42); after the 0.19 field-fix cycle (2026-10-30): **1,053 of 117,634 blocked**, 151/151 load, 116,581 supported incl. 60,161 staged, zero compile errors - zero delta vs `blocked-catalog-rt5d-main` (no corpus table uses `moAlwaysHideChildren`, so the new `hidden_children` marker changes no plan; catalog re-run `blocked-catalog-019-field`) |

### Portable frozen-build fix (2026-10-10)

The frozen converter failed to locate
`dependencies/native/mono-api-source/api-prototypes.json` when running
from the portable ZIP (path did not resolve outside the source tree).
Fix: `mono_runtime.py` gained a frozen-aware
`_default_export_table_path()` (resolves against `sys._MEIPASS` in frozen
mode, `parents[3]` in source mode); `native_build.py freeze()` now bundles
`api-prototypes.json` into both EXEs via `--add-data`. Regression
coverage: `tests/test_native_mono_runtime.py` class
`PinnedTablePathTests` (source + frozen path resolution). User-verified:
portable converter now generates a trainer EXE inside the ZIP.

### 0.15 prefix-cut coordinator-window fix (2026-10-18, part 2)

Field report (Great Circle table, trainer build `0.15-ext2`, debug log
`Indiana Jones and the Great Circle (0.15-ext2).ct2debug.log`,
2026-10-18): every formerly broken entry now toggles — except
**Stealth Mode (ID 24)** and **No Reload (ID 19)**, both still rejected
with `Entry patch cuts or contains an invalid instruction`. The traceback
locates the rejection in the publish path, not staging:
`hooks.publish` → `DebugEventCoordinator._check_overwrite_windows` →
`hooks.validate_entry_control_flow` applied to the 2-byte prefix-cut
receipts, where **both** sides (original `0F 87`/`0F 84` and replacement
`90 E9`) are instruction fragments. The part-1 fix (`d15268a`) made the
stage-time gate accept the shape, but the coordinator's overwrite-window
check (and the thread-IP exclusion range) still ran the strict
complete-instruction contract on the fragment receipt — so the fix never
survived publish. Also observed in the same log: an engine-blocked
receipt drift (`ReadProcessMemory failed (Win32 error 299)`) after the
two failed toggles; consistent with a target-side change and covered by
the existing module-snapshot fallback, no code change required.

Fix: `link_program` extends a proven prefix-cut receipt to the full first
original instruction. `_entry_prefix_cut` (already decoding the live
window and proving the patched stream) now returns the live tail bytes
(patch end → first original instruction boundary) instead of a bare
bool; the block then carries original = complete jcc (6 bytes) and
bytes = patch + unchanged tail (`90 E9` + original rel32 =
`nop; jmp` to the same target). Every downstream layer — coordinator
window check, thread-IP exclusion (now the full instruction, not 2
bytes), restore on disable — sees complete instruction sequences on both
sides, so the historical strict contract is unchanged everywhere. The
`prefix_cut` flag remains for provenance and the stage-time live
re-proof still covers any un-extended receipt. Fails closed on every
doubt exactly as before. Tests: `tests/test_native_assembler.py`
(link-level extended receipt, enable + disable),
`tests/test_native_debug_coordinator.py` (extended receipt passes the
strict window check; un-extended fragment stays refused),
`tests/test_native_hooks.py` (stage → publish through a coordinator that
runs the real `_check_overwrite_windows`). Focused suites 109 OK;
full local run: failure set identical to the pre-fix baseline
(pre-existing local-environment gaps only). The released 0.15 ZIPs
(`native-20261018T055505Z-39f20180`) predate this fix; the re-cut
build carries it. No table change required — the field table keeps the
build-independent `db 90 E9` entries.

### 0.16 field fixes: WP-58 UI startup crash + Sinking City 2 runtime chain (2026-10-20)

Field report (user testing of the first 0.16 build, 2026-10-20; trainer
`Indiana Jones and the Great Circle (0.16).exe` + debug log): every
0.16-generated trainer crashed at startup with
`TypeError: tkinter.Button() got multiple values for keyword argument
'height'` — the engine init completed fine (providers listed, clean
close), the crash is in WP-58 UI construction.

Two WP-58 regressions in `src/ct2trainer/native/ui.py`:
1. `TrainerWindow._button` hard-coded `font=`/`height=2`/`pady=4` as
   literal `tk.Button` kwargs on top of the `**style` spread; the
   `_chip` call (filter chips) passes `width=9, height=2,
   font=("Segoe UI", 11)` → duplicate `height`/`font` keywords →
   `TypeError` during `_build_filters` in `TrainerWindow.__init__`,
   i.e. before the first render. Fix: defaults merged into the style
   dict; caller kwargs now override them.
2. The pagination buttons pass the tuple `padx=(0, 4)` as a widget
   option (valid only for `pack`/`grid`) → `TclError: bad screen
   distance "0 4"` — a second latent startup crash that only became
   reachable after fix 1. Fix: padding moved to `.pack()`.

Regression coverage: `tests/test_native_ui_button.py` (3 tests, real
tkinter widget construction for every `_button` call-site signature —
the mock-based UI tests never exercised widget construction). Full
suite 3398 OK / 25 skips / 0 failures.

Sinking City 2 "activate" step (user report: the activation chain
"does not work correctly ... there are attach functions that are not
supported yet"): plan-level re-measurement (headless
`tools/native_corpus_audit.py` over the local-only table, 34 entries)
shows **34/34 supported, 0 blocked, 9 actionable** — the `OpenProcess`
attach call (record id 200) is supported since WP-56 as a truthy no-op
with process-name identity verification (named mismatch refusal), the
pointer record (id 1337270331) is a regular two-phase AOB provider
(first-match per WP-55), and the "Talents" value (id 31) is staged
behind it (WP-14 gate). The runtime chain is now proven end-to-end on
owned fake memory with the real Lua host:
`tests/test_native_sc2_attach_chain.py` (2 tests: one-shot attach
record → multi-match AOB pointer provider → staged pointer value;
byte-exact patch restore, symbol release, staged gate re-lock, named
refusal on process-name mismatch). No new converter/engine capability
required — the observed failure mode is the 0.16 UI startup crash (the
trainer never reached the activation step) and/or pre-Wave-4 builds
where `OpenProcess` was still unsupported. One `LuaRuntime` per
activation keeps CE parity for record 198's compact mode (function
defined in ENABLE, called in DISABLE). Field note: a runtime
"pattern not found" means the table's AOB pattern is absent from the
installed game build (table/build mismatch, fail-closed by design —
cf. the 2026-10-18 Sinking City 2 analysis, Inf Items). Case-32 pin
decision (root, cycle-end per WP-57 row): no new corpus pin — the
chain's plan-level shapes are already pinned (case-31 + existing
categories); the runtime combination is covered by the new engine test.

### 0.16 field fixes (round 2): state-lock self-repair and reliable restart (2026-10-21)

Field report (user testing of the 0.16 field-fix re-cut
`native-20261020T150115Z-c426fb92`, 2026-10-21; trainer
"The Sinking City 2 (0.16).exe" plus debug log, 48 events, state dir
`4b6b2825f4296e83`, table sha256 `f52e0d06…`, target
`TheSinkingCity2.exe` pid 15404): the re-cut mostly worked — the new
WP-58 UI was confirmed good, attach (19:00:33) and 5 restored wishes
plus toggles 200/18/198 were fine. Two findings:

1. **One cheat did not work: Inf Items (record id 15, symbol `IITEMS`,
   AOB `8B 42 48 41 2B C0`)** — `ScanMiss` twice in the debug log
   (19:01:23, 19:01:46). The table targets "Steam version 1.0
   Build.24671220"; the installed build does not contain that pattern.
   Table/build mismatch, fail-closed by design — correct behavior, no
   code fix (same record already identified in the 2026-10-18 SC2
   analysis).
2. **Trainer could not be restarted after closing** — "state.lock
   already exists" (three attempts at 19:18:13 / 19:18:20 / 19:18:24,
   plain `StateError` from engine.py line 866). Root-cause chain from
   the log:
   - 19:15:53 the target exited while the poll tick was verifying hook
     receipts: `ReadProcessMemory` failed with Win32 error 299
     (`ERROR_INVALID_STARTING_ADDRESS` while the process unmapped) →
     `PatchConflict` → engine blocked. The blocked poll early-returns
     (`engine.py` poll guard), so the target-exit cleanup path never ran.
   - 19:16:15 the user closed the trainer: `close()` hit the blanket
     `if self.blocked or self.busy: raise` guard and refused → the
     state lock was orphaned.
   - The atexit net could not release it either: `_StateStore.close()`
     refuses while `session_bytes` is set ("Cannot release state
     ownership while a process session remains"), and the exception was
     swallowed.
   - At the 19:18 restarts the stale-lock probe classified the lock as
     the generic "delete that folder" refusal: the owner (pid 9304) was
     proven dead, but the full `assess_recovery` was not eligible — all
     recorded identities (owner *and* the session target) must be
     proven dead in two observations, and `MAX_ASSESS_SECONDS = 15`
     leaves no room to explain the reason to the user. A transient
     "unknown" probe flake had earlier produced the same plain refusal
     (18:58:12 plain → 18:58:20 recoverable on the same lock, 8 s
     apart).

Fixes in `src/ct2trainer/native/engine.py` (this change):

1. `TrainerEngine.close()`: the block guard now refuses only while the
   target is still alive (`self.memory is not None and
   self.memory.is_alive()`). With the target gone — or never attached —
   the normal exit cleanup runs (finish-after-exit for all scopes,
   session and lock released, `state.json` wishes preserved), logged
   as `close-after-blocked`. A still-alive target keeps the fail-closed
   refusal, because its still-applied patches must stay recoverable.
2. `_atexit_close`: when the store still owns lock plus session at
   interpreter exit and the memory handle proves the target gone, the
   session is released before the lock. While the target is alive (or
   unknown) the state is preserved untouched for the verified
   stale-state recovery on the next start.
3. `_stale_lock_probe`: a single transient "unknown" owner observation
   is retried once after 1.5 s before the conservative refusal. When
   the owner is proven dead but the full assessment is not eligible
   (most commonly: the previous session's target is still running), the
   refusal now carries the top assessment reasons plus an actionable
   hint (close the previous target, then restart — the verified
   recovery dialog is offered once every recorded process is proven
   dead) instead of the generic "delete that folder" line.

Regression coverage: `tests/test_native_stale_lock_selfheal.py`
(7 tests: blocked close with gone target completes and releases
lock/session while preserving `state.json`; blocked close with alive
target stays refused; atexit net releases session+lock on a provably
gone target and preserves everything on an alive target; stale-lock
probe retries a transient "unknown" owner probe and recovers; a
persistently unproven owner still gets the conservative refusal; an
ineligible assessment — owner dead, target alive — yields an
actionable refusal naming the reason and the state directory).
`tests/test_native_engine.py::test_different_trainer_variants_cannot_share_one_live_target`
updated: a never-attached blocked variant now releases only its own
state lock on close (it owns no session or patches) while the shared
target lock stays with the attached engine.

Full local dev suite after the change (CT2TRAINER_NASM set):
**3405 OK / 25 expected skips, 0 failures** (previously 3398/25 after
the round-1 field fixes).

### RT-1: full-corpus rebaseline (2026-10-21)

First roadmap package of the 100% reference-table cycle:

1. **Frozen input manifest** `gap_inventory/reference-manifest.json`
   (committed; dev material, not shipped): all 151 local-only
   reference-table paths with SHA-256 (143 distinct hashes), byte size,
   format (`ct` vs `legacy-binary`), the exact target EXE binding
   (ct-suggestion from `process_detect.find_candidates`, `game.exe`
   default when the table carries none) and the architecture inference.
   Snapshot stamp 2026-10-21, source revision `ea233c2`.
2. **Catalog re-run on the current 0.16 source** (local-only artifacts
   `blocked-catalog-rt1.json` / `.md` in the refassess scratch dir):
   151 tables, 117,624 plan entries, 114,926 supported (58,950 staged),
   **2,698 blocked**, one whole-table load error (SuperMeatBoy.CT legacy
   binary) — **identical per table to the 2026-10-20 post-Wave-4 run**
   (zero drift in entries, supported/staged/blocked, reason counts and
   process bindings), so the 0.16 lock self-repair change has no catalog
   effect.
3. **Stale prose repair** in the committed `gap_inventory/` baseline:
   the `15 pinned start-corpus tables` scope string and the
   `27 pinned tables` gate/note strings were stale since the 25th-30th
   corpus pin. Fixed at the tool source
   (`tools/corpus_denominator/__main__.py`,
   `tools/corpus_denominator/feature_matrix.py`) and the committed
   `gap-report.json` / `feature-coverage.json` / `ap11-campaign.json`
   regenerated under the pinned run id
   `w4b4-case30-20261020081722Z`; the repro chain
   (`tests/test_native_repro_chain.py`) stays byte-identical and the
   feature-matrix and AP-11 tests pass.

### RT-2: residual attribution of all 2,698 blocked rows (2026-10-21)

Second roadmap package of the 100% reference-table cycle. A subagent lane
performed the attribution on the RT-1 catalog (`blocked-catalog-rt1`)
against the frozen manifest and the local-only reference corpus; the root
integrator re-verified every class sum and per-table sum in both
directions (each totals exactly 2,698) and independently re-ran the
lane's corrected UNDEFINED-split logic. Final classification: the
lane's `rt2_final2` run, superseded in wording by the lane's final
report (2026-10-21 21:14, `RT2_FINAL_REPORT.md`), which is the
authoritative record: verified per-family roots for the 963 AA-hidden
rows (entry-level cross-reference), the a-d classification legend, and
seven caveats.

**Decomposition:** 2,698 = 1,931 provider-cascade rows + 767 direct
rows. Cascade terminals: 1,304 undefined-symbol rows - 963 AA_HIDDEN
(in-table registrations whose provider entry is blocked before symbol
extraction; verified per-family roots span digit-leading labels,
cleanup-ownership chains, dup-label/dup-provider roots, quoted
module+offset defines, Lua-registered symbols, and Type:Member
bounds), 110 LUA_RUNTIME (table Lua `registerSymbol` providers), 91
NO_REG (no static registration evidence; user-side symbols,
cross-table loading or dynamic Lua; optional user-symbol import), 128
LEGACY_SYM (user-expected legacy symbols with no built-in CE 7.5
handling - BaseAddress, stat names, module names without .exe - plus
the x87 `st(0)` FPU-operand misparse and keyword false positives),
12 API_EXPORT (Win32 exports) - plus 624
duplicate-provider cascades (600 = five shared UE5 template tables x 120
`character_pointer`) and 3 wildcard-cleanup conflicts. The 2026-10-20
queue's leading reason occurrences decompose exactly: `Esau_base` (600)
-> duplicate-provider cascades; `mouse_ovr` (84) + `loot_ptr` (62) ->
AA_HIDDEN in the Witcher3 pair; `BaseAddress` (80) -> LEGACY_SYM across
the five UE5 template tables; pointer offsets (53) -> direct
hex-literal refusals.

**Per-class testable contract, risk and expected delta** are recorded in
the [RT-2 root-cause map](../plans/reference-table-100-roadmap.md)
(section "RT-2 root-cause map"), with the RT-4 package split (lane
final report) summing exactly to 2,698: RT-4.1 symbol provider
fidelity 820, RT-4.2 runtime provider model 1,085, RT-4.3 address
expression & identifier dialect 452, RT-4.4 value semantics 65, RT-4.5
AA directive & script coverage 57, RT-4.6 input legacy & authoring gaps
219; suggested order RT-4.1, RT-4.3, RT-4.4, RT-4.5, RT-4.6, RT-4.2
last. Headline parity findings (all three open CE probes closed):
dropdown overflow - CE 7.5 truncates, never refuses
(`MemoryRecordUnit.pas:3200-3574` `SetValue`, `pb^:=StrToQWordEx`);
bare module references without `.exe` fail in CE 7.5 too
(`TSymhandler.getAddressFromName`, `symbolhandler.pas:4985-5103`,
exact match with extension kept) - input-legacy/user-config;
`BaseAddress` has no built-in CE 7.5 handling (user/Lua-defined
symbol); `usemono` has zero hits in the 7.5 tree (newer-CE directive);
IL2CPP `Type:Member` atoms resolve only via registered symbols or the
pipe-server C (no native static resolution, `PipeServer.cpp/h`).

Static evidence only; no code change in this package.

### 0.16.1: Sinking City 2 table-load warnings + versioning rule (2026-10-21)

Field finding: loading `TheSinkingCity2.CT` (CheatEngineTableVersion 46)
surfaced three plan warnings that read like failures although the table
loads and works (34/34 supported, 0 blocked in the static compile):

1. **"Table version 46 is newer than the local CE reference (45)…"** —
   stale reference constant. CE 7.5, the behavior reference, writes
   `_CurrentTableVersion = 45` (`OpenSave.pas`); 46 is issued by newer CE
   builds. Field verification: the SC2 table compiles clean, and 13 of
   the 30 pinned corpus tables are already v46. Fix:
   `LOCAL_CE_TABLE_VERSION` 45 → 46 in `src/ct2trainer/table.py`;
   genuinely newer versions (e.g. 47) still warn. The pinned v52 test
   table keeps its warning, now against reference 46
   (`tests/test_native_compiler.py`).
2. **"At least one Auto Assembler script contains {$LUA}."** — reworded
   to state the supported behavior: the embedded Lua runs in the
   trainer's built-in Lua runtime when the record activates (the WP-56
   record-Lua path is the designed execution path, not a defect flag).
3. **"At least one script invokes a dialog or external action and needs
   review."** — split per API: `ShellExecute` (the SC2 support-link
   record) now reports the documented safe no-op (WP-56, no external
   program or URL is launched); `messageDialog` — not implemented by the
   native Lua runtime — keeps a real review flag naming the activation
   failure. `Entry.external_action_apis` carries the matched API names;
   `capability.py`'s machine-readable risk names are unchanged.

Regression tests: `tests/test_native_sc2_table_warnings.py` (7 tests:
the SC2-shape v46 table carries exactly the two informational warnings
with 0 blocked records; v46 emits no version warning; v47 warns against
46; `{$LUA}` informational wording; ShellExecute no-op wording;
messageDialog gap wording; both-API case).

Versioning rule (user decision 2026-10-21): every build gets a new
version number — feature releases bump the minor, bug-fix builds bump
the patch (0.16 → 0.16.1 → 0.16.2). Recorded in `AGENTS.md`; `VERSION`
and `__version__` bumped together to 0.16.1
(`tests/test_native_version_display.py` enforces the match).

Full local dev suite after the change (CT2TRAINER_NASM set):
**3,412 OK / 25 expected skips, 0 failures** (previously 3,405/25 after
the 0.16 field-fix round 2). Built as
`native-20261021T161241Z-b0566a25` (in-build 3,412/25, `ce_inputs: []`,
first build under the rule).

### 0.16.2 field fix: recovery journal schema (WP-57 captured_placeholders) (2026-10-22)

Field report (user testing of the 0.16.1 portable build, 2026-10-21;
debug log `The Sinking City 2 (0.16-3).ct2debug.log`, trainer
`4b6b2825f4296e83`, table SHA-256 `f52e0d06041aa0b0…`, target
`TheSinkingCity2.exe`): the trainer did not start at all — `state.lock`
from a prior session (trainer PID 9304, verified terminated) was still
present, and the recovery assessment stayed blocked with three identical
reasons, one per hook journal in `state/hooks/` (hex-named receipt
files): "Recovery record contains missing or unknown schema fields".
The refusal repeated on every startup attempt; the only way out was
deleting the state folder (user instruction in the error message).

Root cause: WP-57 (`4f89562`, shipped in 0.16) added the
`captured_placeholders` field to the hook journal document written by
`hooks.py` (captured bytes of `s<N>.<M>` AOB placeholder tokens), but
`recovery.py::_hook()` — the journal schema validator used by
`assess_recovery` — was not updated with that field. Its `_fields`
check rejects every unknown field, so every journal with non-empty
captures failed the assessment. Any trainer with
placeholder-capture hook entries therefore could not start after a
prior session left `state.lock` behind (crash, kill, or the 0.16
field-case orphan lock); the refusal was deterministic and repeated on
every attempt. Pre-0.16 journals (no such field) were unaffected, which
is why the block surfaced with the 0.16 series. The engine's own
startup receipt checks (`engine.py`) only parse and finalize existing
journals, so the stale session was never noticed before the recovery
assessment; `recovery_operation.py` re-runs `assess_recovery`, so the
transaction path was affected in the same way.

Fix (clean-room, minimal): `recovery.py::_hook()` now lists
`captured_placeholders` as an optional journal field and validates its
shape with the writer-side contract
(`patterns.validate_placeholder_captures`: at most 16 captures,
casefolded `s<N>` names, 1-2 hex bytes per value). A malformed
captures mapping still blocks with the named refusal "Hook journal
placeholder captures are invalid".

Regression tests: `tests/test_native_recovery.py` (+2): a hook journal
with valid `captured_placeholders` stays eligible for read-only
recovery (field case, reproduced locally before the fix), and
malformed captures (bad hex, non-placeholder name, odd byte length)
stay blocked with the named reason.

Full local dev suite after the change (CT2TRAINER_NASM set):
**3,414 OK / 25 expected skips, 0 failures** (previously 3,412/25).
Merged to `main` on the field-fix branch
`native-0.16.2-sc2-state-recovery`; built as
`native-20261022T160328Z-0423fb21` (0.16.2, cut from `main` @
`68eeb00`, in-build 3,415/25, `ce_inputs: []`). User workaround if
still on an older build: with the game closed and the previous trainer
process verified terminated, delete the trainer's state folder
(`%LOCALAPPDATA%\CT2Trainer\native\<trainer_id>`) to start fresh.

### 0.16.3 field fix: Sinking City 2 activation failure (2026-10-22)

Field report (user testing of the 0.16.2 portable build, 2026-10-22;
debug log `The Sinking City 2 (0.16-4).ct2debug.log`, trainer
`4b6b2825f4296e83`, table SHA-256 `f52e0d06041aa0b0…`, x64 controller
against the x64 target `TheSinkingCity2.exe`): "total failure — the
trainer did not activate at all". Two independent defects compounded:

1. **Startup block (0.16.2 brick class, second field):** the state
   directory held three hook journals from a prior 0.16-series session
   (hex-named receipt files `2dd1f087…`, `701e2488…`, `cde6a43b…`).
   Since WP-47/55 (`ee07b60`, shipped in 0.16) the journal writer
   persists a `value_data_ranges` span list on **every** allocation
   entry (the initial allocation dict in `hooks.py::allocate()`,
   appended by `declare_value_data`), but `recovery.py::_hook()` — the
   journal schema validator used by `assess_recovery` — did not accept
   the field. The 0.16.2 fix had added only the sibling
   `captured_placeholders` field. Every allocation-bearing journal
   therefore failed with "Recovery record contains missing or unknown
   schema fields" and blocked recovery behind the stale `state.lock`;
   the refusal repeated on every startup attempt until the state
   folder was deleted manually.
2. **Activation failure:** after a fresh state, the attach to a
   freshly started game succeeded, but the first entry scan failed
   nine milliseconds after attach: `CreateToolhelp32Snapshot
   architecture modules failed (Win32 error 24)` with both the
   combined 0x18 and the native-only 0x08 flags. Error 24 is
   `ERROR_INVALID_ID` — the documented transient form of
   module-snapshot creation while the target's module list is still
   changing (DLLs loading right after start; CreateToolhelp32Snapshot
   Remarks: the call "may fail with ERROR_BAD_LENGTH or another error
   code … try calling the function again"). The `memory.py` retry
   loop was doubly broken: (a) `ERROR_BAD_LENGTH` was mislabeled as
   24 (the documented transient code is 1116), so the documented code
   was never retried; (b) the mislabeled retry was a tight
   3-attempt loop without backoff, useless while the module list is in
   flux. The engine blocked (entry scan) and the later close re-raised
   the stored block error (fail-closed, per design), leaving a lock
   the restart assessment correctly refused while the target was
   alive.

Fix (clean-room, minimal):
- `memory.py`: corrected the constants (`ERROR_BAD_LENGTH = 1116`,
  `ERROR_INVALID_ID = 24`, `ERROR_MORE_DATA = 119`);
  `_take_module_snapshot` now retries a bounded 8 attempts with
  exponential backoff (0.05 s doubling, 1.0 s cap, ~3.5 s worst case)
  on the transient set {1116, 24, 119}; non-transient errors still
  fail fast. The architecture-only retry flag is now
  architecture-aware (0x08 for a 64-bit target, 0x10 for a
  32-bit/WOW64 target, which lists its modules only under
  `TH32CS_SNAPMODULE32`), and the final dual-failure message carries
  both failure codes.
- `recovery.py::_hook()`: accepts `value_data_ranges` as an optional
  allocation-entry field and validates it against the writer contract
  (list of at most 4096 exact `{address, size}` spans; each span
  inside the allocation's `[address, address + actual_size or size]`
  bounds; no duplicate span; an unlocated allocation cannot carry
  spans). Malformed inventories keep named refusals.

Regression tests: `tests/test_native_architecture.py` (+4):
transient 24 is retried with backoff until success; 1116 (the
documented code) is retried; a persistent transient error exhausts
2×8 attempts and fails with the named dual-flag message; an x86
target falls back to the 0x10 flag. `tests/test_native_recovery.py`
(+2): a writer-shape allocation journal with in-bounds
`value_data_ranges` stays eligible for recovery; six malformed
shapes (non-list, non-dict span, missing size, below/above the
allocation, duplicate span) stay blocked.

Full local dev suite after the change (CT2TRAINER_NASM set):
**3,421 OK / 25 expected skips, 0 failures** (previously 3,415/25).
Merged to `main` on the field-fix branch
`native-0.16.3-sc2-field`; cut as 0.16.3 build
`native-20261023T065015Z-afbc3eba` (in-build suite 3,421 OK / 25
expected skips, `ce_inputs: []`, `runtime_unverified` deliberately
kept per gate; source ZIP sha256
`0b34c4f3797095aefcba66a45d46216596e816817ea1b98208a42a5217df2e5a`,
portable ZIP sha256
`bb495a6f61538051b8caeac14394bdc80b7b165b946f34f3ae710524e37fd0a3`).

### RT-4.1 symbol provider fidelity (2026-10-22)

Package RT-4.1 of the reference-corpus closure cycle (roadmap
"RT-2 root-cause map", branch `native-rt4-1`, merged to `main`
2026-10-22): CE `dupIgnore` provider fidelity — keep-first without
blocking duplicate provider entries, repeated names inside `label()`
lists, wildcard-cleanup scoping. Expected class delta 820 (R1 624, R2 3,
O2 186, O16 4, O17 3); measured net delta **-840** (842 unblocked, 2
explained regressions).

**Code** (clean-room, four source files):

1. `compiler.py::_dependencies` — keep-first duplicate-provider
   policy: a second entry registering an already-registered symbol is
   no longer blocked wholesale. Its duplicate registration is shadowed
   (removed from the symbol's provider list; first supported provider
   wins in document order) while every non-duplicate registration in
   the same entry still takes effect, so dependents resolve against the
   kept provider. CE reference (read-only): `dupIgnore`
   (autoassembler.pas:338/345) dedupes only the per-program
   disable-symbol list, and the AA runtime registration is
   delete-then-add (autoassembler.pas:4164-4208) — CE is last-wins;
   keep-first is the documented safe narrowing
   (`runtime-parity-assessment.md:257`). The
   `shared_provider_compatible` shared-global path is unchanged:
   compatible shared-global declarers share, and external consumers are
   not ambiguously admitted (pinned by
   `test_native_global_engine::test_compatible_duplicate_declarers_share_
   without_ambiguous_external_admission`).
2. `aa_program.py::prepare_program` — repeated names inside one or more
   `label()` declarations are now tolerated: CE's duplicate-declaration
   check is disabled (autoassembler.pas:2585-2586); multiple `name:`
   definitions (2599) and never-defined names (2603) are still refused,
   and unresolved label references still fail fail-closed in the
   linker.
3. `aa_program.py` — the wildcard-cleanup static guard is removed; the
   wildcard sweep is scoped at runtime to the program's own
   phase-owned symbols (the wave-B wildcard re-derivation loop and its
   reason/source constants are gone with it).
4. `engine.py` — runtime registration is keep-first as well: the first
   activated registrant owns the symbol, a later duplicate registration
   is a silent no-op, and the duplicate releases nothing on disable;
   the plan gates were updated to the same keep-first policy (the
   `_install_program` collision raise is gone; unselected duplicates
   stay inert at runtime).

**Tests:** nine focused modules (provider selection/dedupe, compiler,
global engine, Lua symbol handover/provision, one-shot Lua providers,
symbol self-provision, user-defined symbols) 167 OK; full local dev
suite on `main` after the merge: **3,415 OK / 25 expected skips, 0
failures** (CT2TRAINER_NASM set, 2026-10-22).

**Catalog delta** (local remeasure, run `blocked-catalog-rt41`, frozen
manifest `gap_inventory/reference-manifest.json` and process bindings
unchanged; baseline `blocked-catalog-w4b4.json`): **2,698 -> 1,858
blocked of 117,624** (net −840; supported 114,926 -> 115,766; staged
58,950 -> 59,642; the one legacy-binary load error unchanged). 842 rows
unblocked, by baseline reason class: all 624 R1 duplicate-provider
cascades (600 `Esau_base` + 24 non-template cascade rows across the
qt-ds trio, Cyberpunk, ForgottonAnne, SHProto), all 3 R2
wildcard-cleanup rows (Octopath2 `mem0x04`), all 186 O2 direct
duplicate-provider rows, 2 of 4 O16 dup-label rows (re2 /
re2_testicles `dCusWetAmount`), and 47 R3 rows whose duplicate root
cleared (LADG 26 `pbase`, AtomicHeart v1.2 21). Per-table highlights:
HellPie 140 -> 18, Scorn 140 -> 17, Oregon 141 -> 17, Callisto 140 ->
17, AtomicHeart v1.2 166 -> 20, LADG 30 -> 0, SOTTR 65 -> 29, qt-ds
trio 41 -> 4, Borderlands3-V10 30 -> 16, APlagueTaleInnocence 7 -> 0,
Octopath2 333 -> 327.

**Regressions:** exactly 2 supported rows, both explained —
Cyberpunk2077 ids 380/381 ("If Iconic Weapon / Item Level 1/2") now
refuse with "Required symbol has no unique supported provider:
weaponPtr": keep-first leaves all three compatible
`globalalloc(weaponPtr,$32)` declarers (741/379/382) supported, so the
external value records are no longer ambiguously admitted — the pinned
shared-global contract. In the baseline these two rows resolved only by
accident: the duplicate providers had been blocked earlier at the
`weapon`/`weaponBkp` register-symbol duplicates, dropping them from the
`weaponPtr` candidate set before the shared-global check ran. Net:
**zero unexplained supported regressions** (package protocol
satisfied).

**Witcher3 note:** the two O16 dup-label rows (4.02HF1 / 4.03, id 10281
"Item Pointers (Mousover Inventory and Loot)" in 4.02) now compile past
the `label(return loot_ptr mouse_ovr code return str_ptr)` duplicate but
are blocked at the next gate: `str_base` is a Lua-generated `define`
(`return string.format("define(str_base, %X)", string_static_base)` in
the `{$LUA}` block) the static compiler cannot resolve — runtime-
provider class (R3 root spans RT-4.2/4.5). Not a regression: both rows
were already blocked in the baseline (reason moved from the dup-label
refusal to the missing-provider refusal), so the `mouse_ovr`
(41/43), `loot_ptr` (31), `player_ptr` (11) and `st` (1) cascades
remain for RT-4.2. Three further rows per table surfaced new downstream
reasons previously masked by the duplicate block (createthread gate,
`GetAsyncKeyState`, `str_base`) — blocked-to-blocked moves only; two
duplicate-provider rows per table (return1/return2) unblocked.

**case-28 plan state** (pinned synthetic corpus, re-verified on the
RT-4.1 tree): total 10 / supported 9 / actionable 9 / blocked 1,
e[59] "Required symbol has no unique supported provider: SynthOnly28"
— pre-existing non-dup class, unchanged by RT-4.1.

Static evidence only; runtime activation of the keep-first policy on an
owned target is RT-6 scope.

### RT-3 legacy-binary CT format (2026-10-23)

The last table-load gap: `SuperMeatBoy.CT` (10,328 bytes, magic
`CHEATENGINE\t`, CE 5.x-era pre-XML binary format) was refused by the XML
reader. The lane (`native-rt3`, commit `2703d59`, merged to `main`
2026-10-23) added a clean-room parser `src/ct2trainer/legacy_ct.py`:

- The true magic is **11 bytes**; the 12th byte is the low byte of the
  version DWORD, so the former 12-byte `CHEATENGINE\t` constant in
  `table.py` matched only version-9 files by accident. Format versions
  6-9 are verified against the reference layout; version >9 loads with an
  "assumed unchanged" warning, version <6 is refused as too old.
- Truncation (with exact offset + remaining bytes), corrupt magic, and
  implausible counts/lengths (record count 20000, pointer count 256,
  code-record count 4096, description 4096, interpretable 4096, script
  4 MiB) are named `LegacyCTError` refusals — a `TableError` subclass, so
  inspection diagnostics keep G4a for every unparseable legacy input.
- `read_table` dispatches magic-matching files to the parser; everything
  else keeps the unchanged XML path. The parser emits a standard-XML
  document (`Table.converted_xml`, unserialized) that flows through the
  unchanged, fully tested XML pipeline — record semantics, activation
  safety, warnings are not re-derived; `compile_table` consumes the
  converted XML when present.
- Source identity stays the original binary bytes: `Table.source_sha256`
  and the plan `table_sha256` are the binary's SHA-256 (matching the
  frozen reference manifest), never the converted XML's.
- Record IDs are synthesized in document order (top-level records in
  file order, then "Group N" headers in numeric order with their
  members); pointer records keep the last pointer's address plus the
  full offset chain (intermediate pointer addresses are not
  XML-expressible, documented); legacy code records become CheatCodes.

Tests: 28 new in `tests/test_native_legacy_ct.py` (byte-level field parse
including the full variable-type code map, conversion document
order/IDs/groups, pointer offset + address survival, CheatCodes byte
blocks, `read_table` identity and dispatch semantics, trailer and
newer-version warnings, grouped records, 9 named refusal cases, plan
byte-stability across recompiles, selection by synthetic ID, and an
engine-level value write + AA enable/disable roundtrip proven byte-exact
on fixture memory) plus updated legacy pins in
`tests/test_native_table_robustness.py` (the 96-byte fixture now decodes
as version-9/10-records truncated at offset 94; version<6 too-old
refusal). Full suite on `main` after the merge: **3,450 OK / 25
expected skips**. The real `SuperMeatBoy.CT` loads with all 10 exact
labels, 10/10 supported, and the 897-byte trailer warning (local-only
reference test, skipTest when absent).

**Catalog delta** (local remeasure, run `blocked-catalog-rt3`, frozen
manifest and process bindings unchanged): **151/151 tables load** — the
one legacy-binary load error is cleared; total 117,624 -> 117,634,
supported 115,766 -> 115,776 (the 10 `SuperMeatBoy` records, 0 staged,
0 blocked), staged unchanged 59,642, blocked unchanged 1,858. The other
150 tables are byte-identical per-table: zero regressions.
`runtime_unverified` remains: the 10 AA records' real-game effect is
untested (standing gate; the owned-target proof is RT-6 scope).

### RT-4.4 value semantics (2026-10-23)

Package RT-4.4 of the reference-corpus closure cycle (roadmap
reference-table-100-roadmap.md; branch `native-rt4-4`, commit
`6ebdb8a`, merged to `main` 2026-10-23) closes the value-class rows
O6/O7/O8/O26 per the CE 7.5 `SetValue` conclusions:

- **O6 DROPDOWN_WIDTH (30 rows: P3R/v4/v5 9 each, P3Reload 3):** CE
  `SetValue` (MemoryRecordUnit.pas:3500-3503) parses the choice string
  with `StrToQWordEx` and stores it through the typed pointer — CE
  truncates an out-of-width choice instead of refusing it (choice '314'
  on a Byte writes low byte 0x3A). The width is no longer checked at
  plan time; `engine.parse_value` truncates every integer write to the
  record width (`(number & ((1 << size*8) - 1)).to_bytes(size,
  "little")`). Decimal mode parses a decimal regex first, then a hex
  fallback; hex mode stays hex-only and fails closed.
- **O8 DROPDOWN_EXPR (13 rows: Borderlands3-V10 12, P4G 1):** bracketed
  choices on simple-numeric records compile to `expression: True`, are
  validated by `parse_expression` at plan time (both the compiler and
  the engine plan validator, byte-identically) and are pre-resolved
  against the runtime symbol table before any write. The bracket
  condition is strict (starts `[`, ends `]`, length > 2), matching CE
  SetValue 3449-3450. Alternate-base hex choice IDs on decimal records
  are accepted as writable literals — a deliberate documented clean-room
  extension, because CE's `StrToQWordEx` (parsers.pas:248) would route
  a bare hex-looking decimal through the float path and error.
  Unparseable choices keep the refusal on writable records and become
  display rows on read-only dropdowns.
- **O7 STRING_SHOWASHEX (8 rows unblocked: DS2 2, HorizonForbiddenWest
  3, HorizonForbiddenWest (1) 3):** string records with ShowAsHex stage
  a `byte_array` value profile (hex byte display, ShowAsHex/
  ShowAsSigned/ShowAsBinary carried in properties). CE copies raw text
  on vtString (MemoryRecordUnit.pas:3534-3587); the byte-array staging
  is the documented clean-room interpretation of the O7 row.
- **O26 DROPDOWN_EMPTY (0 reference rows; class implemented and
  synthetically tested):** read-only dropdowns with empty or
  placeholder-only choice lists stage as display-only views (the `*`
  placeholder drops out, possibly-empty choices allowed) instead of
  refusing.
- **O11 CUSTOM_TYPE (6 rows) stays gated by design** (AP-08.7 gate;
  refusal messages pinned).

Plan metadata: `writable: False` (display-only row) and
`expression: True` (expression choice) markers on dropdown rows,
enforced byte-identically by both plan validators. Tests: 18 new in
`tests/test_native_value_semantics.py` (byte-exact engine-level pins on
memory.data/memory.writes — signed wraparound '-1' on 4 Bytes ->
`ff ff ff ff` displayed 4294967295, '70000' on 2 Bytes -> `70 11`,
decimal '01E7' on 2 Bytes -> `e7 01`, hex-mode fail-closed, expression
pre-resolution before any write, read-only empty-set write refusal, O7
byte-array roundtrip, O26 empty placeholder staging) plus pin updates
in `test_native_dropdown_separators.py`, `test_native_value_types.py`,
`test_native_compiler.py` and `test_native_engine.py` per lane-rules
6a. Full suite on `main` after the merge: **3,471 OK / 25 expected
skips**.

**Catalog delta** (local remeasure, run `blocked-catalog-rt44`, frozen
manifest and process bindings unchanged): **1,858 -> 1,807 blocked** of
117,634 (net -51; supported 115,776 -> 115,827; staged 59,642 ->
59,683; 151/151 tables load, zero compile errors). Exactly 51 rows
unblocked, all in the expected classes: O6 30, O7 8, O8 13. Zero newly
blocked rows. Eight rows change only their immediate block reason and
stay blocked on the pre-existing symbol-provider gate: DS2 25521/
25524/25526 (ShowAsHex string pointer records on the blocked `p`
provider), DS2 87558/87561/87563 (blocked `myPtr3`), DS2 87598 (blocked
`myPtr2`) and 小猫咪，大城市 id=3 (the empty-dropdown row now reaching
the blocked `CatValues` provider behind 小猫咪 id=2 `usemono`). No
plan-level providers involved; zero supported regressions.

### 0.16.4 field fix: trainer crash observability (Sinking City 2, 2026-10-24)

Field report (user testing of the 0.16.3 portable build, 2026-10-23;
debug log `The Sinking City 2 (0.16.3).ct2debug.log`, table
SHA-256 `f52e0d06…`, x64 controller against the x64 target
`TheSinkingCity2.exe`): on PC2 the trainer process (pid 10528) died
**silently mid wish-restore** — the last logged event was the TALENTPTR
aobscan at 18:49:31, and nothing followed: no engine-close, no
engine-blocked, no crash record. The restart attempt at 18:50:06 was
refused by the state lock while the game was still alive (the correct
fail-closed behavior). Recovery proof from the same session log: after
the game was restarted, session 12692 (19:16) restored TALENTPTR
successfully at 19:16:55, entry 15 IITEMS handled its transient
attach-time ScanMiss (the game was still loading) per-record, and the
user toggled without issue at 20:25.

Root-cause conclusion: every Python-level failure path in the trainer
logs an event (`engine-blocked`, `engine-close-failed`,
`attach-attempt-failed`, …) — none appeared, so the silent death is a
**hard exit** (native crash or external kill), not an escaped Python
exception. The TALENTPTR restore itself is not deterministically
broken (it worked on PC1 and on PC2's second attempt). The actual
defect is the missing crash observability of the windowed build:
stderr is unattached, no `sys.excepthook`/`threading.excepthook`
override, no `faulthandler`, and the 250 ms Tk poll callback called
`engine.poll()` without any guard — an escaping exception propagates
out of `mainloop()` and kills the process without a single byte of
evidence.

Fix (clean-room, minimal, four files):
- `debug_log.py`: `TrainerDebugLog.arm_crash_reporting()` installs
  (at most once per process) a `sys.excepthook` wrapper writing a
  `trainer-crashed` JSON event (error + full traceback + pid) and then
  delegating to the previously installed hook, a
  `threading.excepthook` wrapper writing `trainer-thread-crashed`
  (with the thread name), and `faulthandler` enabled on a dedicated
  append handle so native fatal signals (access violation, stack
  overflow, abort) dump every thread's Python stacks into the same log
  file. The crash handle is independent of `close()`, so evidence is
  written even after the engine tore the session log down. Arming
  emits no log event of its own; a re-arm (the startup retry loop may
  create several engines before the session engine is final) closes
  the previous handle.
- `ui.py::run_trainer`: arms crash reporting once the final engine
  exists — both entry points covered (frozen launcher, source CLI run
  command).
- `ui.py::TrainerWindow.poll`: wraps `engine.poll()` fail-closed — an
  escaping exception is logged as `poll-crashed`, the engine is
  blocked (writes refuse, the status line names the cause), and the
  250 ms tick keeps scheduling, so the window stays observable and
  recoverable.
- `engine.py`: the restore loop logs `restore-entry-start`
  (identifier + label) before each record's dependencies/enable, so a
  hard process exit mid-restore leaves the last in-progress entry
  identifiable in the debug log.

State-lock behavior is unchanged: the blocked restart while the target
was alive remained the correct fail-closed refusal; this fix only adds
the evidence that was missing.

Regression tests: `tests/test_native_sc2_crash_observability.py` (new,
8 tests): the excepthook writes `trainer-crashed` with the full
traceback; the threading hook writes `trainer-thread-crashed` with the
thread name; faulthandler is armed and survives session close; crash
evidence survives `close()` (the session log itself stays closed); the
hooks are installed once across instances and keep delegating to the
originals; a disabled log does not arm; the poll guard blocks the
engine, logs exactly one `poll-crashed`, and keeps the window ticking;
`restore-entry-start` precedes `wish-restored` for every restored wish.

Full local dev suite on the field-fix branch (CT2TRAINER_NASM set):
**3,479 OK / 25 expected skips, 0 failures** (previously 3,471/25
after the RT-4.4 merge). Merged to `main` on the field-fix branch
`native-0.16.4-sc2-field`; cut as 0.16.4 (build pending).

### RT-4.6 input legacy & authoring gaps (lane `native-rt4-6`, 2026-10-24)

Lane commit `839c1c6` on branch `native-rt4-6` (pinned base `c95c10b`),
merged to `main` on 2026-10-24 (merge commit `7c3149c`, clean three-way
merge over the RT-4.4 + 0.16.4 state, no conflict resolution needed).

- **R5 UNDEF_NO_REG / R6 UNDEF_LEGACY closure:** the `_dependencies`
  zero-candidate branch distinguishes "symbol registered nowhere" from
  "symbol has ambiguous providers". A pure-text registration survey
  (`_symbol_source_survey`: `registersymbol` / `registerlabel` /
  `registerSymbol` call forms including quoted names, line-anchored
  `label(...)`, `define(...)` + `{$define ...}`, positional `name:`
  labels, `aobscan*(...)` first argument) over the raw table source
  decides. No registration found -> actionable per-symbol report
  `Required symbol '<S>' is not registered anywhere in this table
  (referenced by '<record path>'): no record defines it and it is not a
  user-defined symbol. Import it as a user symbol with its target
  address, or add a record that registers it
  (registersymbol/registerSymbol/label/aobscan).`; registration found
  (or more than one supported provider) -> the generic `Required symbol
  has no unique supported provider: S.` stays byte-identical. The survey
  is fail-safe: malformed syntax can only add registration evidence,
  never remove it. The plan cannot make this distinction itself because
  `_block()` clears `provides`.
- **`st`/`st(N)` FPU-operand fold (2 reference rows):** the AA tokenizer
  folds the x87 operand per CE 7.5 Assemblerunit.pas:3283-3291 parity:
  bare `st` -> `st0`, exactly one digit `st(N)` -> `st0`-`st7`; `st(8)`
  and wider keep the bare token so the symbol machinery still blocks
  fail-closed.
- **User-symbol import:** `compile_table(user_symbols=...)`,
  `load_user_symbols(path)` (JSON: casefolded name -> 64-bit unsigned
  address; named, bounded, fail-closed refusals for non-mapping/oversized
  imports, non-text names, casefold duplicates, non-integer or
  out-of-range addresses, invalid symbol names, non-JSON or non-object
  files, and invalid address strings), CLI `--user-symbols FILE` on
  inspect/prepare/build. Plan field `user_symbols` (schema 2, emitted
  only when non-empty, keys sorted) carries the residual symbols no
  supported record provides (same residual rule as
  `user_defined_symbols`). Engine `_seed_user_defined_symbols` seeds UDS
  first, then user symbols, on init and every confirmed attach; an import
  overrides a table-level definition of the same name. Both plan
  validators (compiler `validate_plan` and the engine wrapper) refuse
  forged maps: shadowing record-provided symbols, out-of-range values,
  duplicates.
- **Documented deviations beyond the R5/R6 split** (lane audit): +2
  RiftApart `HeroHealthVFTable` and +2 Witcher3 `str_base` are
  legitimately unregistered -> new-style report; DS2
  `InventoryItemProperties_call_dest` and Horizon Forbidden West
  `Sleep` x2 stay generic (bare `call` targets). Lane classification
  audit over all 1,284 zero-candidate rows: 1,038 generic / 217
  new-style / 0 misclassified.
- **Known root-owned defect (out of lane scope) — RESOLVED 2026-10-26,
  no defect exists (root audit; see the audit section below):** the
  lane reported the pinned NASM 3.02 as mis-encoding the FSTP fpureg
  table entry (`x86/insns.dat:751` `FSTP fpureg [r: dd d8+r]`, measured
  `fstp st0` -> `DD D8`, expected `DF C0`). The audit against the Intel
  SDM instruction table and the pinned MIT iced-x86 decoder shows the
  expectation was wrong: **FSTP ST(i) is encoded as `DD D8+i`**
  (`DD D8` decodes as `fstp st(0)`; `DF C0` is FFREEP ST(0)). With the
  explicit `bits 32`/`bits 64` directives the pipeline always emits,
  every FST/FSTP/FLD register and memory form matches the Intel table
  byte-for-byte; the 0x66/0x67 prefixes seen in the lane's probe runs
  were artifacts of snippets without a `bits` directive (this NASM
  build defaults to 16-bit mode). NASM 3.02 does reject the
  parenthesized `st(N)` syntax outright (bare `st0`-`st7` only), which
  the tokenizer fold works around at link time. The two Witcher3
  `fstp st(0)` rows therefore link and assemble with correct bytes
  (DD D8); regression pins added in
  `tests/test_native_fpu_st_operand.py`.

Tests: 53 new — `tests/test_native_fpu_st_operand.py` (9, including the
runtime roundtrip `fcomip st(0), st(1)` -> `DF F1` enable write on
fixture memory with disable restore of the original bytes),
`tests/test_native_undefined_provider_report.py` (12) and
`tests/test_native_user_symbol_import.py` (32) — plus pin updates in
`test_native_creator_inspection`, `test_native_luacall_symbol_provision`
(x3) and `test_native_placeholder_aob` (the fixtures' symbols are
registered nowhere, so the new classification applies by design). Full
suite on `main` after the merge: **3,532 OK / 25 expected skips**
(baseline 3,479 + 53; clean re-run exit 0).

**Catalog delta** (local remeasure, run `blocked-catalog-rt46`, frozen
manifest and process bindings unchanged): **1,807 -> 1,778 blocked** of
117,634 (net -29; supported 115,827 -> 115,856; staged 59,683 ->
59,709; 151/151 tables load, zero compile errors). Exactly 29 rows
unblocked: `Lust from Beyond -F.CT` id=8 (`st`) and
Witcher3_Complete_Edition_or GOTY_4.02HF1_G25v2.CT x14 /
Witcher3_Complete_Edition_or GOTY_4.03_G25v2.CT x14 (per table: `st` 1
at id=10070 plus the cascade behind the now-supported 'Activate Player
Scripts' provider — player_ptr 11, companion_ptr 1, horse_ptr 1). Zero
newly blocked rows. 218 rows change only their block reason and stay
blocked on the same gate: all 218 move from the generic provider message
to the actionable per-symbol report (the lane's 217 over the RT-3
baseline plus the RT-4.4 reason-changed 小猫咪 id=3 `CatValues` row,
which now also qualifies); 0 rows move back to the generic form. No
supported regressions.

### RT-4.5 AA directive & script coverage (lane `native-rt4-5`, 2026-10-24)

Lane commit `92dd60e` on branch `native-rt4-5` (pinned base `c95c10b`),
merged to `main` on 2026-10-24 after the RT-4.6 merge (merge commit
`885a3b7`, clean three-way merge, no conflict resolution needed).

- **O12 AOBSCANREGION:** `aobscanregion(name, start, end, pattern)` is
  now supported with Type:Member symbol bounds resolved at runtime; the
  `dealloc` name-list follows CE 7.5 semantics — comma/whitespace
  split, silent unknown-name drop, 128-name / 128-character bounds, a
  wildcard takes no other names, numeric size tails tolerated. One
  deliberate divergence kept: cleanup touching foreign symbols or
  allocations stays refused by the ownership gate (documented, stricter
  than CE).
- **O15 USEMONO:** both envelope halves (static AA and Lua) now refuse
  `usemono()` with the named parity-scope refusal 'usemono targets a
  Cheat Engine newer than 7.5; out of parity scope.' (zero hits in the
  CE 7.5 tree).
- **O18 managed labels:** the managed-label regex admits the
  three-segment `Namespace.Class:BaseClass:Method` form via a `{1,2}`
  colon tail; two-segment, `::` and four-segment forms keep the
  established refusal.
- **O19 GLOBAL_INIT:** global DISABLE reset regions — a direct global
  cursor on an initialized global in DISABLE opens a no-op reset whose
  repeated literal bytes must equal the ENABLE initializer; empty
  regions accepted; changed bytes get the named
  changed-reinitialization refusal; non-literal/oversize/double/
  never-initialized/staged-readmem-under-cursor all named.
- **O20 NO_EXEC_PATCH:** symbol-only static envelopes — DISABLE-only
  `unregistersymbol` lines whose names are the record's own luaCall AOB
  symbols are admitted with the deterministic `symbol_only_disable`
  marker; the runtime skips the assembler receipt and releases exactly
  those owned symbols via two-pass `_release_owned_unregister` with
  named refusals; plan-level `one_shot` True vs record-level False.
- **O21 GLOBAL_INIT_LABEL:** label after consumed literal data closes
  the global region into the consumer program; label before data keeps
  the established refusal.
- **O5 CLEANUP_OWNED (diagnostics):** named symbol-handover refusals
  carry the single owning record id via `external_owners` at all three
  re-derivation sites (`compile_script` / `prepare_program` /
  `prepare_lua_program`). Pure-global records (whole body
  globalalloc/initializer/reset) get the canonical empty consumer
  program with a manager-less pool round trip
  (`global_alloc.empty_consumer_program`).

Tests: 30 new — `tests/test_native_global_reset.py` (17),
`tests/test_native_luacall_symbol_only.py` (5),
`tests/test_native_aa_named_refusals.py` (4) — plus pin updates in
`test_native_assembler`, `test_native_address_tokens`,
`test_native_managed_method`, `test_native_aa_literals` and
`test_native_lua_symbol_handover`. Full suite on `main` after the
merge: **3,562 OK / 25 expected skips** (baseline 3,532 + 30; clean
re-run exit 0).

**Catalog delta** (local remeasure, run `blocked-catalog-rt45main`,
frozen manifest and process bindings unchanged): **1,778 -> 1,743
blocked** of 117,634 (net -35; supported 115,856 -> 115,891; staged
59,709 -> 59,735; 151/151 tables load, zero compile errors). Exactly 35
rows unblocked: Subnautica_e67616 x28 (4 `aobscanregion` rows plus 24
provider-cascade rows now registered by the supported directive),
TheSinkingCity x2 (O19 id=14780, O21 id=258093), SOTTR x2 (O20
symbol-only envelopes), Resonance x1 (O19 id=14780), Shinkansen
Sunless Sea V1005 x1 (O18 Type:Member atom, id=112473), RDR2 x1
(id=48136). Zero newly blocked rows. Seven rows change only their block
reason and stay blocked on the same gate: ForgottonAnne id=0/103886
and 小猫咪 id=1/2 onto the named usemono parity-scope refusal;
Subnautica_e67616 id=89 onto the ownership gate (deliberate
divergence); Sunless Skies id=29 onto the trailing-tokens refusal;
TheSinkingCity id=258084 onto the changed-reinitialization refusal
(`bFastTravel`). No supported regressions.

### Trainer UI: Scripts view and row context menu (root, 2026-10-24)

User-requested feature (2026-10-24), implemented on branch
`native-0.17-ui-script-inspector` cut from `main` @ `42f7fb6`; UI-only
change — plan format, engine contract and catalog untouched.

- **`Scripts` view** (sixth filter chip; `VIEWS` in `ui_layout.py`
  5 -> 6, `FILTER_CHIP_COLUMNS_WIDE` 5 -> 6, the narrow 2x3 chip grid
  under 650 px width is now exactly full,
  `_VIEW_ROW_HEIGHT["Scripts"] = ROW_HEIGHT_SWITCH`): lists every plan
  entry with `kind == "script"` regardless of selected/supported —
  supported scripts as normal switch rows, blocked and unselected
  scripts as dim 48 px info rows with their exact reason; heading and
  value records hidden, group sections kept as structural rows.
- **Row context menu** (right-click `Button-3` on any row, or the
  existing 400 ms long-press, which now opens the menu instead of the
  Info dialog directly): "Script preview" and "Copy script text"
  (both only when the entry carries executable source), "What is
  happening here" (assessment dialog), "Details" (the existing Info
  dialog, content unchanged). Works on switch, value, section and dim
  info rows alike.
- **Pure builders** in the new `src/ct2trainer/native/ui_script_view.py`
  (no Tk, no engine): `script_backing()` classifies the executable
  form (`program` / `lua_program` / `global_program` / `operations` /
  None — blocked records carry no executable source by plan
  contract); `script_preview()` returns (window title, body) — the
  raw `source` text for program/Lua/global entries (exactly what will
  run) and, for operation lists, the normalized phases rendered one
  operation per line; `entry_assessment()` renders the deterministic
  plain-language read from plan metadata: status (supported / not
  selected / staged pending-or-satisfied via the live applied set /
  blocked), last action error (window-supplied), converter reason,
  staged gate with provider labels, program form with bitness,
  enable/disable operation counts and capabilities, one-shot flag,
  provides/requires, depends-on (via `dependency_ids`) and
  required-by (via `provides` intersection with other entries'
  `requires`), activation-set summary, source hotkey count and the
  runtime-verification flag. Both dialogs are read-only `ScrolledText`
  `Toplevel`s on the existing dark palette; "Copy script text"
  reports in the status line.
- Docs updated in the same change:
  `documentation/trainer-ui-design.md` (D3/D7/D8/D9 updates + new
  section 8), `documentation/usage.md` (chips + context-menu usage
  guide), `tests/deck/compatibility-matrix.md` (touch checklist and
  layout description).

Tests: 25 new — `tests/test_native_ui_script_view.py` (23: backing
detection per form, exact preview titles/bodies for all four forms,
pinned assessment texts for supported/staged-pending/staged-satisfied/
blocked/unselected/value/heading/one-shot/activation-set entries),
`tests/test_native_ui_rows.py` (+2: Scripts view lists every script
record only; headings and values hidden) and
`tests/test_native_ui_layout.py` (`window_columns` wide mode 5 -> 6,
docstrings). Full suite on the branch: **3,587 OK / 25 expected
skips** (baseline 3,562 + 25; clean run exit 0). Catalog remeasure
(run `blocked-catalog-ui-scripts`, frozen manifest and process
bindings unchanged): **zero delta** vs `blocked-catalog-rt45main` —
151/151 load, 117,634 total, 115,891 supported (59,735 staged),
1,743 blocked, zero compile errors, zero newly blocked/unblocked,
zero reason changes (UI-only change, plans byte-identical). The
feature ships in the 0.17 build, cut after the remaining RT-4.x
merges (RT-4.2 1,085) per the user decision 2026-10-24.

### NASM 3.02 FSTP encoding audit (root, 2026-10-26)

Root audit of the "FSTP defect" recorded by the RT-4.6 lane (bullet in
the RT-4.6 section above). Result: **no defect in the pinned NASM
3.02; the original "expected" encoding was wrong.**

- **Pin integrity:** `.tools/native-tools/nasm.exe` sha256
  `04ec2385879f7e1c45dbe76c4020970555de48eeb97c23f59620ede061328f51`
  = the manifest executable hash; a fresh download of the official
  archive `nasm-3.02-win64.zip` (nasm.us) hashes to
  `161d0bfaff53c2f9e9f3e69fd0672323ebabafd1268976a5cec11be92a19aee7`
  = the manifest win64-zip hash, and its `nasm-3.02/nasm.exe` member
  hashes to the same `04ec2385...`. `nasm -v` reports "NASM version
  3.02 compiled on Jun 28 2026". The pin is the genuine official
  build; the identical FSTP/FST lines exist in upstream NASM master
  (`x86/insns.dat`), so any table error would be upstream-wide.
- **Intel SDM instruction table (reference, Dec-2023 revision):**
  `FSTP ST(i)` = `DD D8+i`, `FST ST(i)` = `DD D0+i`, `FLD ST(i)` =
  `D9 C0+i`; memory forms `FSTP m32` = `D9 /3`, `FSTP m64` = `DD /3`,
  `FSTP m80` = `DB /7`, `FST m32` = `D9 /2`, `FST m64` = `DD /2`,
  `FLD m32` = `D9 /0`, `FLD m64` = `DD /0`, `FLD m80` = `DB /5`. The
  pinned MIT iced-x86 decoder agrees independently (`DD D8` ->
  `fstp st(0)`, `DD D0` -> `fst st(0)`, `D9 18` -> `fstp dword
  [eax]`, `DD 18` -> `fstp qword [eax]`, and `DF C0` -> `ffreep
  st(0)` — the "expected" `DF C0` is in fact FFREEP ST(0)).
- **Measured with the pinned binary:** with the explicit
  `bits 32`/`bits 64` directives that CT2Trainer always emits
  (assembly generation in `aa_program.py` starts every program with
  `bits {bitness}`), every probe instruction matches the Intel table
  byte-for-byte: `fstp st0` -> `DD D8`, `fstp st1` -> `DD D9`,
  `fst st0` -> `DD D0`, `fld st1` -> `D9 C1`, `fadd st1` -> `D8 C1`,
  `fcomip st0, st1` -> `DF F1`, `fstp dword [eax]` -> `D9 18`,
  `fstp qword [esp]` -> `DD 1C`, `fst dword [eax]` -> `D9 10`,
  `fld qword [eax]` -> `DD 00`.
- **Root cause of the false alarm:** the lane's probe snippets
  omitted the `bits` directive; this NASM build defaults to 16-bit
  mode (control: bare `mov eax, 1` -> `66 B8 01 00 00 00`, `mov
  dword [eax], 1` -> `67 66 C7 00 01 00 00 00`), which adds 0x66/0x67
  operand/address-size prefixes to every instruction — the source of
  the unexplained `0x67` prefixes in the earlier readings. No
  CT2Trainer program ever assembles without the bits directive, so
  the trainer payload was never affected.
- **Consequence:** the two Witcher3 `fstp st(0)` rows (one per 4.0x
  table) assemble correctly end-to-end (token fold `st(0)` -> `st0`,
  then `bits 32` program -> `DD D8`); no re-pin, no local patch, no
  compiler-side workaround needed. New regression pins:
  `tests/test_native_fpu_st_operand.py` (+3: assembler-level byte
  pins for the FSTP/FST register and memory forms over the pinned
  binary with explicit bits directives, plus a full-pipeline engine
  roundtrip of the exact corpus line `fstp st(0)` -> `DD D8` enable
  write with disable restore). Full local suite after the change
  (CT2TRAINER_NASM set): 3,590 OK / 25 expected skips
  (baseline 3,587 + 3, clean run exit 0); catalog remeasure
  `blocked-catalog-nasm-fstp-audit` zero delta vs
  `blocked-catalog-ui-scripts` (docs + tests only, no functional
  change).

### RT-4.3 address expression & identifier dialect (lane `native-rt4-3`, 2026-10-26)

Lane work (branch `native-rt4-3`, base `4b9f359`) executed to
completion by the root integrator after the lane subagent stalled;
rebased onto `main` @ `29adebb` with four conflicts resolved:
`address_expression.py` keeps main's bounded `{1,2}` managed-label
tail from RT-4.5 (O18) plus the lane's `is_managed_label`,
`_HYPHEN_MODULE` (negative lookahead) and `_DIGIT_LEADING_SYMBOL`
atoms; `aa_program.py` keeps the lane's `_HYPHEN_MODULE_OPERAND`
(tokenizer level, no lookahead) plus main's `_ST_REGISTER`;
`tests/test_native_address_tokens.py` keeps main's pinned four-segment
refusal row; `tests/test_native_managed_method.py` keeps main's
three-segment admission and four-segment refusal with the merged
RT-4.5/RT-4.3 comment.

- **O1 RELADDR_SKIP (331 class, 195 rows cleared):** a
  relative-address record whose intermediate ancestors are addressless
  script/value records now skips them and adopts the nearest
  address-bearing ancestor, staging `address="(base)+offset"` with
  `address_profile="expression/v1"` and no symbol requires. The WP-38
  provider-group shape keeps its named relative refusal. Forged or
  dangling markers fail closed at the plan gate.
- **O9 RELADDR_NO_ANC (10 class, 8 rows cleared):** relative records
  with no static address-bearing ancestor stage as
  address-required-at-runtime — the group heading carries
  `runtime_base_target=True` and the value carries
  `runtime_base_required=True` plus `runtime_base_anchor=<heading id>`;
  the plan cross-check (`_runtime_base_marker_ok`) refuses forged or
  dangling markers; the engine's `set_dynamic_address` writes the
  anchor only from a supported addressless `kind=script` writer scope,
  with named refusals for non-anchor records, out-of-range values and
  missing bases.
- **O3 PTR_OFFSET_HEX (53 class, 51 rows cleared):** pointer-offset
  slots that are supported address expressions stage verbatim and
  resolve against the live symbol table at activation
  (`_resolve_pointer_offset` expression branch); hex literals are
  unchanged and malformed forms keep the expression-aware refusal
  ("Pointer offset must be a hexadecimal integer literal or a
  supported address expression.").
- **O10 SYM_CHARS (8 class, 5 rows cleared + cascades):** digit-leading
  symbol names (`8PathSteal`, `20XX`) and dot-bearing names are
  admitted per the CE `label()` contract — `validate_symbol` accepts
  `[A-Za-z0-9_.]+` and refuses only fully-hex names (the ambiguous
  `val('$'+name)` case); the `address_expression` tokenizer gains the
  `_DIGIT_LEADING_SYMBOL` atom (a non-hex character must follow the
  leading digit run, so fully-hex tokens stay integers) and the
  `_HYPHEN_MODULE` atom (hyphen module basenames; the trailing negative
  lookahead keeps `.exe`/`.dll`-qualified export atoms whole).
  Provider-lookup cascades on now-parseable symbol names cleared 90
  further rows.
- **O23 QUOTED_ATOM (1 row, stays blocked):** quoted atoms must be
  module basenames; the refusal now names the offending token
  ("Quoted atom '$proces' must be a module basename (.exe/.dll)."),
  a reason-changed row, still blocked.
- **O27/O4 Type:Member and trailing-token atoms (38 rows cleared):**
  multi-segment `A:B:C` and `Namespace.Class:BaseClass:Method` managed
  labels (bounded `{1,2}` tail per RT-4.5 O18) resolve through the
  injected IL2CPP resolver with the per-label named refusal
  ("IL2CPP resolver returned an invalid address for A:B:C." when the
  live binding is missing); the Sunless Skies O27 row cleared.
- **O13 INDIRECT_DATA (5 rows cleared):** directive-aware string data
  bytes — `db` one ANSI byte per char, `dw` UTF-16LE words of any
  length, `dd`/`dq` ANSI chars packed little-endian and zero-padded
  into one unit (CE string semantics); the external-literal engine
  path admits the pure-literal program as committed-RW data with
  sealed per-block permits and the byte-exact disable restore.

Tests: dedicated `tests/test_native_address_expression_dialect.py`
(+20: export-atom tokenization incl. the
`NativeHookFixture.exe.fixture_result` suffix-preserving case,
digit-leading/dot/hyphen grammar, O3 plan + engine chain with
forged-slot fail-closed, O1/O9 staging E2E with forged markers, O27
resolver E2E, O13 byte-exact engine writes) plus pins in
`test_native_address_tokens.py` (+2), `test_native_compiler.py` (+1),
`test_native_pointer_offset_forms.py` (+2),
`test_native_single_quote_data_literals.py` (+2),
`test_native_assembler.py`, `test_native_managed_method.py`,
`test_native_user_defined_symbols.py`,
`test_native_user_symbol_import.py` (O10 identifier-contract pins),
`test_native_dynamic_address_provider.py`,
`test_native_process_aob_label.py`,
`test_native_aa_literals.py`. Lane final suite: 3,613 tests, only the
3 known path-dependent non-main failures, 25 expected skips. Full
suite on `main` after the merge: **3,613 OK / 25 expected skips**
(clean run exit 0; merge-base baseline 3,590). Catalog remeasure (run
`blocked-catalog-rt43-main`, 2026-10-26, frozen manifest and process
bindings unchanged): **1,743 -> 1,351 blocked** of 117,634 (net -392;
supported 115,891 -> 116,283, staged 59,735 -> 59,868; zero load
errors, zero newly blocked rows; 12 rows reason-changed, all still
blocked and explained). Composition of the 392 unblocked rows: O1 195,
O3 51, O4/O27 atoms 38, O9 8, O13 5, O10 direct 5 plus 90 dependent
symbol/provider rows; leading per-table unblocks: Octopath_Traveler2
193, DS2 33, Cyberpunk 30, SOTTR 11, Callisto V1.1 9,
SandFallFinalFRF 40 across the five variants, LikeaDragonIshin pair
15. The residual O1/O9 rows (136 + 2) keep their terminal reason:
their chain carries no static address-bearing ancestor — the base is
supplied by an addressless runtime script (RT-4.2 runtime provider
model); the O1/O3/O4/O9/O10/O13 grammar roots they carried are fixed.

### RT-4.2 runtime provider model (lane `native-rt4-2`, 2026-10-27)

Lane work (branch `native-rt4-2`, base `0a471a2`, single commit
`9e092dc`; the original lane session stopped after a status-only reply,
the relaunched session completed the WIP that root had pre-verified:
compiler.py, engine.py, lua_symbol_providers.py,
tests/test_native_undefined_provider_report.py).

- **R3 KEEP_FIRST_FALLBACK:** when the kept (document-order first)
  provider of a non-compatible duplicate-provider set is itself blocked
  for an unrelated reason, a dependent record re-resolves against the
  keep-first scope and the first still-supported candidate takes over
  the requirement (the dependent's activation ordering follows that
  provider, so static resolution and runtime registration stay in
  agreement). Single-candidate symbols are unaffected (the classic
  generic reason stays), and the shared-global (compatible) duplicate
  branch keeps its ambiguity refusal. Catalog-neutral on the corpus at
  this stage: no blocked keep-first provider row exists.
- **R4 MIXED_DIALECT_RELEASE:** release evidence is also collected from
  the `kind == 'asm'` parts of the [DISABLE] phase — the AA
  `unregistersymbol(` form, multi-name per call (CE 7.5 splits the
  argument list on commas/whitespace, autoassembler.pas:2492), the
  wildcard `*` contributes no named evidence and scalar trailing
  arguments (true/false/nil) are excluded. The strict-pair Lua
  `unregisterSymbol` regex is unchanged and stays the only Lua release
  evidence (the CE handler gates on parameters == 1,
  LuaHandler.pas:5292 — a 2-/3-argument Lua call is a no-op). This
  unblocks records whose Lua side registers the symbol and whose
  `{$asm}` envelope releases it in the AA form (the corpus shape behind
  the 286-row R4 delta).
- **R7 API_EXPORT_REGISTRY:** a bounded Windows API export registry —
  bare `call` targets in the registry (GetAsyncKeyState, FindWindowA,
  both user32.dll; registry bound 1..32 entries, growth = casefolded
  entries) compile to supported records carrying the exact `api_exports`
  plan marker (export spelling -> module basename); both plan validators
  refuse forged markers (bounded nonempty mapping, PE basename modules,
  must reference a record requirement, no duplicate casefold names);
  the engine resolves each export against the attached target's live PE
  export table at link time
  (`ProcessMemory.resolve_export`, memory.py:844) with the byte-exact
  5-byte relative call encoding; a live registered symbol of the same
  name always wins without re-resolution, the bare name never enters
  the shared symbol map, and an absent export fails closed with a named
  refusal before any target memory is touched (the failed enable stays
  visibly inactive and is not a saved wish). Disable retains the
  allocation (retention policy, same contract as
  `test_native_allocation_only_enable`).

Tests: dedicated `tests/test_native_rt42_runtime_provider.py` (865
lines, 21 tests: R3 plan 4 incl. the shared-global ambiguity pin, R4
plan 3 + extractor 6 incl. wildcard and scalar-tail exclusions and the
MAX_PROVIDERS valve, R4 engine 1 full roundtrip, R7 plan 3, R7 validate
1 / 7 sub-cases forged markers, R7 engine 3) plus the R7 pin migration
in `tests/test_native_undefined_provider_report.py` (+1, 1 -> 2: the
supported registry row pins `api_exports`, `requires` and empty
`dependency_ids`; the outside-registry row keeps the generic reason).
Lane final suite: Ran 3,635 / 3,632 OK / 25 skipped (only the 3 known
path-dependent non-main failures). Full suite on `main` after the
merge: **3,692 OK / 25 expected skips** (merge commit `bb86983`).
Catalog remeasure (run `blocked-catalog-rt42-main`, 2026-10-27, frozen
manifest and process bindings unchanged):
**1,351 -> 1,053 blocked** of 117,634 (net -298; supported 116,283 ->
116,581, staged 59,868 -> 60,161; zero load errors, zero newly blocked
rows; 28 rows reason-changed, all still blocked and explained — the
reason advances to the next unresolved bare target after the resolved
one: Sleep 24, ShowWindow 2, PlayerCharacter 1, and DS2 id 25478 whose
resolved Trampolines provider exposes the missing user label
UseItem_skip). Composition of the 298 unblocked rows: R4 Lua runtime
symbol providers 286 — DS2 118 (myPtr 44, myPtr3 28, myPtr2 17,
g_GameModule 10, g_DSPlayerSystem 8, Trampolines 4, g_* globals),
HorizonForbiddenWest 82 per copy (BoardGameBoardUnit 20,
LevelBasedXpArray 10, mProperties 10, g_GameModule 11, Trampolines 7,
g_* and component symbols), ForgottonAnne dMoveValueMultiplier 2,
Witcher3 bIsLevel 1 per copy — now staged for runtime resolution; R7
GetAsyncKeyState bare-call rows 12 (ForgottonAnne 7, trine2 3,
Witcher3 1 per copy) supported with the api_exports plan marker and
link-time export resolution; R3 catalog-neutral. 288 of the 298 rows
are now staged and 10 plain supported, plus 5 previously
supported-plain rows moving to staged (the record's address now
resolves through a supported runtime provider at activation: HFW
'Disable All Bound Checks' x2 copies via the [ Initialize ] script,
trine2 x3 via the newly supported parent script).

Open items carried (not wired this lane):

- **R7 entry-patch install contract:** a bare `call` as the entry patch
  of an owned allocation is plan-supported but refused at install by
  the pinned return-context contract
  (`tests/test_native_debug_coordinator`); the corpus-realistic shape
  is a cave trampoline with a `jmp` entry, which is what the engine
  tests cover. Plan-level catalog classification is unaffected.
- **autoAssemble arg2 host parity:** the CT2Trainer Lua host requires a
  falsy second argument (targetSelf guard), while CE 7.5 also accepts
  the corpus's table `disableInfo` as arg2 (LuaHandler.pas:2853; corpus
  form `autoAssemble(body, false, disableinfo)`). Recorded open, no
  behavior change this lane.
- **API-export registry scope:** deliberately minimal (2 entries,
  user32.dll only); the bounded 1..32 marker contract is in place, so
  extension is a registry-entry change, not a contract change.
- **Live export table unverified on real game processes** (owned-target
  evidence only; the fixture export table is synthetic).

RT-4 is complete; the residual blocked rows carry table-side symbols
registered only by the tables' own runtime Lua (globals outside the
clean-room provider set), user labels, bare targets beyond the bounded
API-export registry (Sleep, ShowWindow, ...) and the deliberate gates
(thread capability, cleanup-ownership, addressless ancestors).

### RT-5 item A: embedded `<Files>` extraction and Lua surface (lane `native-rt5-a`, 2026-10-28)

The embedded-`<Files>` extraction and the surrounding Lua surface landed
(merge `479977c`). A new clean-room module
`src/ct2trainer/native/embedded_files.py` implements the CE-7.5 dual-branch
codec: an exact `Encoding="Ascii85"` attribute decodes the CE-alphabet
Ascii85 text to a raw-deflate stream carrying a 4-byte little-endian size
prefix that must match the remaining payload; any other or missing
`Encoding` value takes CE's hex branch (hex text -> raw deflate, read until
EOF, no size prefix), verified against `luafile.pas::createFromXML`. The
per-file content bound is 4 MiB (one `readStringLocal` call must return the
whole file; it tracks the per-call transport limit); the per-table total
stays at 16 MiB.

`table.py::_parse_embedded_files` decodes every entry fail-closed — one
undecodable entry aborts the table load with a named `TableError`;
`EmbeddedFile` + `Table.embedded_files` project through `to_dict`. Duplicate
names are tolerated (CE table-load parity). The compiler emits
`embedded_files` casefold-sorted, only when non-empty; both plan validators
re-derive hash and size from the stored text (schema-1 plans cannot carry
them). The engine seeds `_embedded_files` / `_embedded_by_name` at init via
`setdefault` (case-sensitive exact-name, first-occurrence-wins).

`lua_host` adds `findTableFile`/`FindTableFile` (nil when absent; dual
`stream.memory` / `file.Stream` access shapes), `readStringLocal`
(token-based `ct2tf:`/`ct2ss:`, strict UTF-8), the `stringstream.*` surface
(create/copyFrom/dataString/size/destroy, per-scope registry, 256-object /
16 MiB bounds), `tablefile.delete` and `createTableFile` fail-closed refusals,
and the stringlist `Text` getter/setter (CRLF-to-LF, positional split keeping
empty lines, one trailing newline does not add a phantom item, destroy). A
`load`/`loadstring` compat wrapper restricts to string chunks in text mode
(function-chunk and binary-mode refused); `dofile`/`loadfile`/`coroutine`
stay nil. The stringlist `Text` setter had a `gmatch` bug (no captures returns
matched strings, not positions) fixed with a find-based positional loop.

Two `readStringLocal` deviations from CE `readStringEx` are documented and
pinned: omitted/negative maxsize returns the full content (CE defaults to 50
bytes), and there is no NUL truncation because the embedded content is the
asset itself (CE stops at the first NUL).

Tests: `tests/test_native_rt5_embedded_files.py` +53 (codec roundtrip over
all tail lengths + hex-branch roundtrip + exact named decode refusals;
`validate_embedded_files` forgery matrix + hex acceptance + duplicate
tolerance + 64-file / 16 MiB bounds; table-load contract with hex-branch
positive + invalid-hex named refusals + duplicate tolerance + per-file and
total bounds; plan projection casefold-sorted + both validators'
forged-hash/size/schema-1/hex-entry; end-to-end P5 table-Lua shape with a
byte-exact 4641 write and disable restore plus the engine registry seed; the
RiftApart record shape tFileList -> createStringStream -> copyFrom ->
stringlist.Text -> loadstring; readStringLocal maxsize and NUL semantics;
invalid-UTF-8 named refusal; casefold-duplicate case-sensitive resolution;
exact-duplicate first-occurrence-wins; string-stream-token readStringLocal;
12-case refusal matrix with zero memory writes) plus pin updates in
`test_native_lua` (sandbox `load`/`loadstring` wrapper),
`test_native_rt5_no_effect_register` (`<Files>` no longer in the omitted
warnings, exact `embedded_files` projection) and
`test_native_table_completeness` / `test_native_user_defined_symbols`
(`embedded_files` in the completeness contract).

Verification: focused 221 tests across 5 files OK; full suite on `main` after
the merge **3,745 OK / 25 expected skips** (baseline 3,692). Catalog remeasure
(run `blocked-catalog-rt5a-main`, frozen manifest and process bindings
unchanged): **zero delta** vs `blocked-catalog-rt42-main` (151/151 load,
117,634 total, 116,581 supported (60,161 staged), 1,053 blocked, 0 compile
errors, 0 newly blocked, 0 reason-changed). The 9 reference files with a
non-empty `<Files>` section (7 distinct games: P5Strikers + copy, RiftApart,
Octopath2, DeathStrandingDC + compatibility, Cronos, Resonance, SinkingCity)
gain `embedded_files` in their plans; zero blocking-status movement.
`runtime_unverified` remains: the embedded-file record effects are untested on
a live target.

Open items carried (not wired this lane): none - all RT-5 item A acceptance
criteria met.

### RT-5 item C: bounded process-info Lua API family (lane `native-rt5-c`, 2026-10-28)

The bounded process-info Lua API family landed (commit `0167825`, merged to
`main`). Eleven APIs implement the CE 7.5 process-info surface under the
clean-room single-target model — every API answers only from the attached
target (plan process binding, attached pointer width, target module table,
bounded memory disassembly); no OS process or module enumeration beyond the
target:

- `getProcessIDFromProcessName`: exact or casefold match against the plan
  process binding returns the attached target pid, anything else 0
  (documented deviation from CE 7.5 answering nil; the corpus tolerates both
  shapes).
- `getProcessList`: single-entry pid->name map resolving the `pl[pid]` and
  `pairs()` corpus shapes (documented single-target bound).
- `getAutoAttachList`: inert per-scope singleton stringlist, fresh per host
  run, reset in `cancel_resources`.
- `getOpenedProcessID`: one-line passthrough alias of `getOpenProcessID`.
- `getSettings`: inert settings object; `Value` answers '' for any missing
  key (CE parity for a missing registry value); writes stored on the object
  and discarded; non-string section is a named refusal.
- `integerToUserData`: identity — addresses are plain integers in the host
  value model.
- `targetIs64Bit`: pointer width 8 -> true, 4 -> false; no arguments.
- `enumModules`: single-module answer with Name/Address/Size/Is64Bit/PathToFile;
  PathToFile falls back to the EXE name when the memory backend reports no
  image path (documented deviation; covers the GoW `for i=1,#modList` shape).
- `disassemble`: bounded iced-x86 exposure over target memory; the CE line
  shape `<8-digit hex address> - <hex bytes> - <opcode operands>` in the
  pinned iced Intel syntax (documented deviation from CE's uppercase style);
  optional second argument count 1..4096 returns the per-instruction line
  list (documented clean-room extension, no corpus usage); named refusals
  for argument count, count bound, invalid instruction and bounded read
  ending first.
- `stringlist_add`: the CE `strings_add` startup-global alias, list-first
  argument order, driving the owned dot-call `.add` contract, returning the
  new 0-based ordinal; named refusal for non-string-list and destroyed list.
- `getCEVersion`: pinned constant string '7.5' (ROOT DECISION; documented
  deviation from CE's number answer; tables use it as a CE-version gate).

Wiring exactly like item A: table-scope `TABLE_LUA_READ_ONLY_NAMES` += the
five dispatch names, record-scope function list += five,
`_ReadOnlyBroker._READS` += five so every pure query is admitted under
syntax checking (all 11 are pure reads, admissible in both the live pass
and the `_disposable_check` syntax-check pass). Every out-of-profile call is
a named refusal with zero memory writes and no applied record. No plan
fields and no engine path changes.

Tests: `tests/test_native_rt5_process_info.py` +23 (byte-exact pid/count/
shape markers via writeInteger read-back, x86 plan plus pointer_size=4 memory
for the 32-bit targetIs64Bit/enumModules/disassemble behavior, byte-exact
disassemble lines incl. the 5-byte mov and the 2-line count form, 14-case
refusal matrix plus 3 standalone disassemble refusals with zero memory
writes and no applied record, out-of-scope names still refused, table-scope
allowlist admits all five dispatch reads with a clean bootstrap); focused
23 OK. Full suite on `main` after the merge **3,790 OK / 25 expected skips**
(baseline 3,767).

Verification: catalog remeasure (run `blocked-catalog-rt5c-main`, frozen
manifest and process bindings unchanged): **zero delta** vs
`blocked-catalog-rt5a-main` (151/151 load, 117,634 total, 116,581 supported
(60,161 staged), 1,053 blocked, 0 compile errors, 0 newly blocked, 0
reason-changed). 44 of the 151 reference tables reference at least one
item-C API (getCEVersion 27 tables / 36 calls, getProcessIDFromProcessName
19 / 35, getProcessList 7 / 14, getOpenedProcessID 6 / 8, getAutoAttachList
5 / 5, targetIs64Bit 5 / 32, enumModules 5 / 6, disassemble 3 / 11,
stringlist_add 3 / 3, getSettings 2 / 4, integerToUserData 2 / 4); the
catalog is unaffected because it is static plan-level and the APIs are pure
runtime host reads. `runtime_unverified` remains: the API answers are
untested on a live target.

Open items carried (not wired this lane): none - all RT-5 item C acceptance
criteria met.

### RT-5 item C2: dynamic addresslist records + custom AA directives (lane `native-rt5-c2`, 2026-10-29)

Dynamic addresslist records and custom AA directives landed (commit
`dbfdcc2`, merged to `main` as `dde9f04`):

- `createMemoryRecord` (AddressList / `getAddressList()` / the built-in
  AddressList index) creates engine-owned session journal entries with
  synthetic IDs above 2**31 - the state store refuses them, so they are
  never persisted; the journal is cleared on target exit and close and
  bounded at 4096 entries.
- The record surface implements the CE MemoryRecord runtime contract the
  corpus uses: Description/Type/Address (integer or expression text
  stored verbatim and re-resolved at read/write time)/Script/Parent
  (self-parent and cycle refusals; deleting a parent promotes children to
  the grandparent)/Child[i] 0-based with out-of-range nil/Offset[i] +
  OffsetText[i] bounded by OffsetCount/Count/Index/OffsetCount/isDynamic/
  Value read-write for vtByte..vtDouble with the named
  out-of-target-range refusal/inert display keys (DropDownList/Aob
  display fields, Color, flat drop-down flags).
- Journal OnActivate/OnDeactivate: 'ct2fn:<n>' function tokens kept in
  the registering host's per-host registry; fired on the real Active
  transition from that host; a stale or cancelled scope logs
  `dynamic-callback-stale` and contains the failure (GoW shape).
- Plan-record OnActivate/OnDeactivate: session-stored tokens fired from
  the shared enable dispatch (after the effect is applied) and the
  disable path (before the record Lua scope closes); plan display
  mutations (Color/Options/ShowAsHex/DontSave/Collapsed/isGroupHeader,
  DropDownList/Aob display fields) are session-stored - the compiled
  plan is untouched.
- `getCEVersion` now answers the number 7.5 (CE 7.5 LuaHandler
  pushnumber parity; the corpus gates numerically - Borderlands3/
  Cygni 'getCEVersion() < 7.x', DS2/HFW 'CEVersion ~= getCEVersion()' -
  and the string usages coerce through Lua; supersedes the item-C
  string pin, tests updated).
- Addresslist lookups: getMemoryRecord (integer = flat 0-based position,
  string = casefolded description per CE getRecordWithDescription
  semantics, absent answers nil), getMemoryRecordByID numeric-string
  coercion, casefolded getMemoryRecordByDescription,
  Count/MemoryRecord[i] out-of-bounds nil, inert selection no-ops
  (SelectedRecord/getSelectedRecord/setSelectedRecord).
- registerAutoAssemblerCommand/unregisterAutoAssemblerCommand:
  table-scope custom AA directive registry (uppercase name ->
  'ct2fn:<n>' token; re-registration replaces; the registry dies with
  the table scope; built-in directive names refused with 'AA directive
  name reserved'; record-scope registration refused named; invalid
  arguments refused named). Expansion runs in `prepare_program` after
  nested-assembly inlining: a line whose uppercased text before the
  first '(' equals the registered name is replaced by the callback
  result (argument = text between the first '(' and the last ')',
  original case; {$define} tokens substituted, word-boundary,
  case-insensitive); CRLF split; nested reprocessing in the same pass;
  nil/empty deletes the line (corpus guard idiom 'if syntaxcheck then
  return end' in the syntaxcheck pass); bounded at 1 MiB result / 4096
  produced lines; strict no-op when no registry is registered, keeping
  every existing plan byte-identical; validate_program/preflight/
  dry_link/link all revalidate against the same registry; nested-
  assembly + custom-directive programs are refused named (no
  composition).
- The helper-install (table-source replay) no-op set extends to the
  journal/session mutation names (record.set, record.delete,
  record.reparent, record.offsetSet/offsetTextSet,
  addresslist.createMemoryRecord, addresslist.setSelectedRecord,
  registerAutoAssemblerCommand, unregisterAutoAssemblerCommand) - the
  live table-scope bootstrap already ran them.

Tests: new `tests/test_native_rt5_dynamic_records.py` +27 (journal happy
path + plan byte-identity, AddressList/getAddressList forms, Child/
Offset 0-based + Delete/destroy/removeFromParent, value read/write,
refusal matrices, GoW OnActivate/OnDeactivate shapes + failure
containment, vtAutoAssembler enable/disable + bad-script refusal,
custom directive end-to-end + replace/unregister + reserved names +
invalid args + registry dies with scope, syntaxcheck refusals,
_expand_custom_commands unit + prepare_program revalidation, journal
lifecycle) plus pin updates in `test_native_rt5_process_info.py`
(getCEVersion number pin; out-of-scope list moved to C2),
`test_native_lua.py` (record.set helper-install no-op subcase),
`test_native_rt5_no_effect_register.py` (getMemoryRecord now supported,
refusal pin superseded), `test_native_table_lua_bootstrap.py`
(record.set records the engine named refusal),
`test_native_aa_literals.py` (prepare_program signature). Focused 27 OK.
Full suite on `main` after the merge **3,817 OK / 25 expected skips**
(baseline 3,790).

Verification: catalog remeasure (run `blocked-catalog-rt5c2-main`,
frozen manifest and process bindings unchanged): **zero delta** vs
`blocked-catalog-rt5c-main` (151/151 load, 117,634 total, 116,581
supported (60,161 staged), 1,053 blocked, 0 compile errors, 0 newly
blocked, 0 reason-changed) - the catalog is static plan-level and the
C2 surface is runtime host behavior. `runtime_unverified` remains:
journal record effects and custom-directive expansion are untested on a
live target.

Open items carried (not wired this lane): none - all RT-5 item C2
acceptance criteria met.


### RT-5 item D: onOpenProcess/onTableLoad callback dispatch (lane `native-rt5-d`, 2026-10-29)

The table's onOpenProcess/onTableLoad callback dispatch landed
(commit `fb1253b`, merged to `main` as `9294bb8`):

- Hook: inside the `meta['executed']` branch of
  `TrainerEngine._run_table_lua_bootstrap`, after the
  `table-lua-executed` event - refused or failed bootstraps retire
  the scope and skip the dispatch.
- CE sequence: `onOpenProcess(processId)` first with the attached
  target PID (`self.memory.pid` as a Lua number - assigned before the
  bootstrap call, always available at the hook site), then
  `onTableLoad(before)` with the Lua literal `false` (documented
  bounded deviation: the once-per-attach bootstrap model has no
  before-load phase, so the callback only ever sees false).
- Each callback is invoked by one pcall-wrapped dispatch chunk on
  the table-scope host: the chunk rawgets the global, returns
  'absent' when missing or not a function, pcall-wraps the call and
  returns 'ok' or 'error: <msg>'; the argument is injected as a
  literal (the PID as an int literal, false literal - no string
  injection); the chunk itself uses only stdlib (rawget/type/pcall/
  tostring), so the table-scope allowlist is unchanged and callbacks
  may call the already-admitted item-C APIs.
- Result handling: 'absent' -> no event; 'ok' -> `table-callback`
  (callback name); 'error: <msg>' -> `table-callback-error`
  (callback name + pcall error text). The corpus shape is contained:
  the Resonance/Sinking City table-local `getTable` helper indexes
  the nil `mForm` global, so the pcall error carries `attempt to
  index a nil value`.
- Invariants: a throwing callback cannot touch `plan["table_lua"]`
  (executed stays True with empty reasons - the clean bootstrap
  stays clean for the dependent record scripts); no new plan fields;
  the second callback still dispatches after the first throws; record
  activation keeps working on the attached target; a Python-level
  host failure logs `table-callback-error` fail-soft and the attach
  continues unblocked.
- Idempotency: one dispatch per confirmed attach (the bootstrap runs
  exactly once per attach with a fresh host) - no extra flag;
  re-attach re-fires on the fresh scope.

Tests: new `tests/test_native_rt5_table_callbacks.py` +9 (CE order +
arguments pinned through the table-scope host read-back, the item-C
game-facing chain, throwing-callback containment, absent and
non-function (`onOpenProcess = 42`) with zero `table-callback*`
events, idempotent across polls, re-attach re-fire, the C2 dynamic
addresslist surface usable from a callback, onTableLoad only ever
false, refused bootstrap skips the dispatch). Focused 135 OK (new
file + `test_native_table_lua_bootstrap` +
`test_native_rt5_dynamic_records` + `test_native_rt5_process_info` +
`test_native_engine`). Full suite on `main` after the merge
**3,826 OK / 25 expected skips** (baseline 3,817).

Verification: catalog remeasure (run `blocked-catalog-rt5d-main`,
frozen manifest and process bindings unchanged): **zero delta** vs
`blocked-catalog-rt5c2-main` (151/151 load, 117,634 total, 116,581
supported (60,161 staged), 1,053 blocked, 0 compile errors, 0 newly
blocked, 0 reason-changed) - the dispatch is runtime host behavior
and the catalog is static plan-level. `runtime_unverified` remains:
the callback answers are untested on a live target.

Open items carried (not wired this lane): none - all RT-5 item D
acceptance criteria met.

### 0.19 field-fix cycle: hotkey-bridge AV fix, value-read observability, describe CLI, staged-options (South of Midnight) (2026-10-30)

Field findings from the 0.18 field tests drove this cycle (branch
`native-0.19-field-fix`, cut from `main` @ `2afbd56`):

- Hotkey-bridge Windows crash (0.18 field report): the real Win32
  hotkey-bridge seam crashed with access violations in the frozen
  environment. Root causes: `HWND_MESSAGE` was set to
  `c_void_p(-1)` (i.e. `HWND_BOTTOM`), which made `CreateWindowExW`
  fail with Win32 error 1400, and several Win32 calls were invoked
  without explicit `argtypes`/`restype`, so ctypes defaulted to 32-bit
  `c_int` and truncated 64-bit `HINSTANCE`/`HWND` pointers
  (AVs inside `RegisterClassExW` / `CreateWindowExW` /
  `DefWindowProcW`). Fix in `hotkey_bridge.py`: `HWND_MESSAGE` is now
  `c_void_p(-3)` (a true message-only window, invisible to
  `EnumWindows`); all Win32 prototypes declare explicit
  `argtypes`/`restype` up front; `RegisterHotKeyW` /
  `UnregisterHotKeyW` are guarded behind a `_hotkey_api_available`
  flag so stripped user32 builds (e.g. some embedded Python
  distributions) can still construct the window lifecycle. `run_trainer`
  logs `hotkey-bridge-started` (with HWND) and `hotkey-bridge-failed`
  debug events.
- Value-read observability (Sinking City 2 field finding): staged
  pointer-chain value reads failed silently (blank "unavailable", no
  trace). `TrainerEngine.read_value` now records every failure as a
  `value-read-failed` debug-log event with the exception, deduplicated
  per identifier per distinct cause (the UI tick retries every visible
  value row per poll - no log flooding), then re-raises.
- New `describe` CLI: `ct2trainer native describe <table>` prints, per
  record, the raw script source, the plain-language assessment and the
  concrete trainer actions (reuses the 0.18 row-details builders from
  `ui_script_view`, so CLI and UI stay in sync); flags `--process`
  (CT suggestion when omitted), `--id`, `--json`.
- Staged-options support (South of Midnight field report: "the staged
  options do not stage - the options should only become selectable
  after the prerequisites are active"): the plan-level staging, the
  engine gates (`_require_staged_live` on value read/write/freeze) and
  the two-level parent cascade (flagged master -> nested child provider
  -> staged values) were proven correct by the new cascade test; the
  gaps were UI-side: (a) a staged-pending value row still opened the
  inline editor on tap - `TrainerWindow._open_value_editor` now routes
  the tap through `engine.read_value` so the engine's named refusal
  ("Staged record 'X' requires active provider 'Y'") lands in the
  status line immediately and the editor never expands; live or
  non-staged values are unchanged; (b) `moAlwaysHideChildren` was not
  implemented anywhere - the compiler now emits the optional
  `hidden_children` plan marker (only for records carrying the option
  with children) and the row model suppresses the flagged entry's whole
  subtree (not the flagged parent row itself) in every view;
  presentation-only, engine-side cascade untouched.

Tests: `tests/test_native_describe.py` +13,
`tests/test_native_staged_cascade.py` +2 (SOM-shaped two-level cascade:
pending refusals -> master ON cascades to the child provider -> both
staged values read/write -> master OFF re-pends both),
`tests/test_native_staged_options_ui.py` +8 (row-model suppression with
a no-flag control plus the SOM shape, and the staged-pending tap guard:
pending refuses and names the provider; live and non-staged open the
editor without touching the engine), `tests/test_native_os_hotkeys.py`
+1 (real-seam connect/register/close lifecycle, Windows-only - an AV
would kill the runner, so reaching the asserts is the regression
signal; skips on builds with stripped user32 exports). Full suite
**3,850 OK / 26 expected skips** (baseline 3,840 + 24 new; the extra
skip is the Windows-only real-seam test in this stripped-build
environment).

Verification: catalog remeasure (run `blocked-catalog-019-field`,
frozen manifest and process bindings unchanged): **zero delta** vs
`blocked-catalog-rt5d-main` (151/151 load, 117,634 total, 116,581
supported (60,161 staged), 1,053 blocked, 0 compile errors, 0 newly
blocked, 0 reason-changed) - no corpus table uses
`moAlwaysHideChildren`, so no plan gains the `hidden_children` marker
and all canonical plans stay byte-stable. `runtime_unverified` remains:
the hotkey-bridge fix and the staged tap-guard are untested on a live
target in this cycle.

Open items carried: none - all 0.19 field-fix acceptance criteria met.

### 0.20 / 0.20.1 branding icons + release-content re-cut (2026-10-30/31)

User request (2026-10-30): replace the placeholder icons with the
user-provided artwork from `C:\Users\xboxl\Desktop\assets\` -
`CT2Trainer_Generator` for the CT2Trainer tool and `Standalone_Trainer`
for the generated standalone trainer .exe files. The third icon set
(`Master_Trainer`) is explicitly out of scope (user decision; the
separate `native-0.20-master-trainer` branch in another worktree
belongs to that future component).

Implementation (commit `6298803` on `main`, branch `native-0.20-icons`
fast-forward merged):

- `CT2Trainer_Generator.ico/.png` copied byte-identical to
  `src/ct2trainer/assets/ct2trainer-converter.ico/.png`: embedded in
  the frozen `CT2Trainer-Converter.exe` via the PyInstaller `--icon`
  flag and set on the converter window at runtime via
  `window_icon_path("converter")`.
- `Standalone_Trainer.ico/.png` copied byte-identical to
  `src/ct2trainer/assets/ct2trainer-trainer.ico/.png`: embedded in the
  `CT2Trainer-Template` stub via the PyInstaller icon, so every
  trainer .exe the converter generates carries it; trainer window icon
  via `window_icon_path("trainer")`.
- 1024x1024 PNG masters committed as reference. `tools/create_icons.py`
  rewritten: it no longer draws placeholder artwork but rebuilds the
  multi-size ICOs (16/24/32/48/64/128/256 px, 32 bpp, PNG-compressed
  entries) from the committed PNG masters, so a rebuild can never
  silently replace the shipped icons (Pillow is a local-only
  dependency, outside the offline wheels; the tool is dev-time only).
- New `tests/test_native_icons.py` (+4): ICO structure contract (7
  entries at 16/24/32/48/64/128/256 px, 32 bpp, intact PNG-compressed
  image blobs), PNG masters 1024x1024, `window_icon_path` resolution
  for both kinds, unknown-kind refusal.
- `VERSION` 0.19 -> 0.20, `src/ct2trainer/__init__.py` `__version__`
  0.20, `CHANGELOG.md` 0.20 entry, README/build.md wording.

First cut attempt (deleted, never shipped): run
`native-20261030T183527Z-8f2cb20a` was cut from the wrong branch - the
build job's branch switch failed because this session's worktree
already held `main`, so the build fell back to `native-0.20-rt5-be`
(without the icon commit) and produced duplicate 0.19 ZIPs without the
icons. The user rejected it ("die neue build verwendet nicht die neuen
icons"); the run directory was deleted before recording and the
canonical re-cut below is the shipped 0.20.

0.20 build (superseded by the 0.20.1 re-cut): run
`native-20261030T184820Z-b9d6dc07` (2026-10-30), cut from `main` @
`6298803` at the canonical path. In-build suite **3854 OK / 26
expected skips** (fully green at the canonical path; the 3
path-dependent baseline-reproducibility tests pass there because their
committed baselines embed the canonical repo path), `ce_inputs: []`,
`runtime_unverified` deliberately kept per gate. The build source
inputs carry the new icon hashes (`ct2trainer-converter.ico`
`a1b7dcd56c17abd40604465ab7977c1cbd350bf977dee7657bb9c8fa8174abe0`,
`ct2trainer-trainer.ico`
`bc434f3004e7d75fd5eef7d9287c30383bd43247d03b741bff039bb42ad60ac9`),
byte-identical to the committed assets; both PyInstaller specs
reference the new ICOs explicitly. PE icon-resource extraction from
both frozen EXEs confirms the icons are embedded: 7 RT_ICON sizes +
RT_GROUP_ICON per EXE, and the largest embedded blob is byte-identical
to the committed ICO's 256-px entry (converter vs
`ct2trainer-converter.ico`, template vs `ct2trainer-trainer.ico`).
ZIPs: `CT2Trainer-0.20-source.zip` sha256
`9ca6dca67b5f7316d8be29b7bab07fa702c9551430f9193c6bf647d052d3ffe3`
(13,326,708 bytes), `CT2Trainer-0.20-windows-portable.zip` sha256
`bddaed809f9771338eac03ed9cb8536f1df6bde23aac0e14cc43009fc61e554a`
(31,313,518 bytes).

Catalog remeasure `blocked-catalog-020-icons` (2026-10-30, canonical
path, all 151 reference tables): **zero delta** vs
`blocked-catalog-019-field` (151/151 load, 117,634 total, 116,581
supported (60,161 staged), 1,053 blocked, 0 load errors) - expected,
since the cycle touched only assets, dev tooling, tests and docs; no
plan-builder code changed.

0.20.1 release-content re-cut (the shipped build): the committed 0.20
changelog suite line described the worktree dev-suite ("all green
except the 3 pre-existing path-dependent baseline-reproducibility
tests") instead of the verified in-build suite, which at the canonical
build path was fully green. Per the 2026-10-21 versioning rule
(every build gets a new version number), the correction shipped as
0.20.1: commit `080128c` fixed the 0.20 changelog suite line to the
verified in-build numbers and cited the `blocked-catalog-020-icons`
remeasure; `VERSION` 0.20 -> 0.20.1; no code or asset changes. Run
`native-20261031T104114Z-d64ae4c2` (2026-10-31), cut from `main` @
`080128c`. In-build suite **3854 OK / 26 expected skips**,
`ce_inputs: []`, `runtime_unverified` deliberately kept per gate; the
new icon hashes again appear in the build source inputs. ZIPs:
`CT2Trainer-0.20.1-source.zip` sha256
`d6ced6ee91fbdd7f12ea4bd6dae92fe49ecf83691c01a867c11279b8f67fb335`
(13,326,889 bytes), `CT2Trainer-0.20.1-windows-portable.zip` sha256
`c8f022b1facec2d3457789a24d2f31583ad9108ee9689148f19615a53d2a31c6`
(31,313,979 bytes).

Open items carried: user field-test of the shipped icons (Windows
Explorer + window icon on the frozen converter, and the taskbar/window
icon of a generated trainer); clean Windows and real Steam
Deck/Proton/touch acceptance remain open; `runtime_unverified`
deliberately kept per gate.

### 0.21: RT-5 complete — CheatCodes code-patch plan path (item B) + messageDialog no-op (item E) (2026-10-31)

Scope: the final two RT-5 inventory items, closing RT-5 in full
(items A, B, C, C2, D, E, F, G all landed). Run under
`documentation/subagent-lane-rules.md`: item B on lane
`native-0.20-rt5-b` (worktree `.worktrees/lane-rt5-b`, root-verified
diff review), item E on root branch `native-0.20-rt5-be`, and the
closing CE-vs-CT2Trainer analysis document on lane
`native-0.20-ce-analysis` (worktree `.worktrees/lane-ce-analysis`).

Implementation:

- Item B (commit `3f1cce3`, merged to `main` as `9ef4a74`):
  fail-closed per-entry `<CheatCodes>/<CodeEntry>` table parse
  (whole-byte hex byte-capture codec with `<Byte>` child and
  whitespace-stripped text fallback, 4096-entry section bound,
  per-entry named drop warnings, `GroupHeader` rows become supported
  heading records — zero in the corpus), `code_patch` plan records
  with synthetic IDs at 2**32+ (above the C2 dynamic-record journal
  range 2**31+1..2**31+4096 — documented deviation from the task's
  2**31 base), CE code-list address forms (`AddressString` verbatim /
  `ModuleName`+offset / absolute hex) with a compile-time static
  symbol-free expression gate, `CheatCodes` added to the
  interpreted-section whitelist, both plan validators re-deriving the
  canonical shape byte-exactly with forged-entry refusals, engine
  lifecycle with named refusals (`code-patch-already-active`,
  `code-patch-target-changed` zero-write refusal,
  `code-patch-restore-mismatch` refusal + engine block; disable
  restores the captured-at-enable original — documented superset of
  CE, which only ever applies `Actual`), executable pages through
  the verified coordinator hook journal, data pages through the
  ordinary byte transaction, standard wish persistence / re-attach /
  close-time restore, `_check_patches` skip, UI switch rows with the
  `code` chip. `tests/test_native_rt5_code_patch.py` +26.
- Item E (commit `a5d0a2f`, merged as `b8bb4ee`): `messageDialog`
  decision = safe logged no-op returning 0 (mbOK, truthy in Lua) with
  the CE 7.5 argument shapes (message / title+message / dialogtype /
  buttons), nil argument tolerance (corpus table Lua passes undefined
  button constants as nil), `message-dialog` debug event, both
  spellings in record + table scope (`TABLE_LUA_READ_ONLY_NAMES`, 47
  corpus table-Lua call sites). `tests/test_native_rt5_message_dialog.py`
  +22 plus pin updates (the SC2 table-load warning pin moves to the
  no-op behavior, the process-info guard keeps the catch-all named
  refusal on a synthetic name, the no-effect register docstrings note
  item E implemented).
- Closing analysis `documentation/ce-vs-ct2trainer-analysis.md`
  (lane `native-0.20-ce-analysis`, `ce0acfc`, merged as `322ae22`):
  CE 7.5 vs CT2Trainer behavior comparison per area, measured end
  state vs the 100% goal, the 17-row bounded-deviation register, the
  RT-6/RT-7 verification path, file:line-verified CE 7.5 citations;
  its final numbers refreshed by this change set.

Verification:

- Suite: full main suite after the item B merge **3,880 OK / 26
  expected skips** (baseline 3,854); after the item E merge **3,902
  OK / 26 expected skips** (baseline 3,880) — 0 failures, verified
  2026-10-31 at the canonical path with CT2TRAINER_NASM set.
- Catalog remeasure (run `blocked-catalog-020-rt5-be`, on `main`
  after the item B merge, 2026-10-31): 117,634 -> 117,809 total,
  116,581 -> 116,756 supported (+175 — every `CodeEntry` of the 22
  tables), 1,053 blocked unchanged, 60,161 staged unchanged, 0 load
  errors, zero newly blocked, zero reason changes (per-table diff vs
  `blocked-catalog-020-icons`: exactly the 22 CheatCodes tables gain
  +175 supported rows). Item E remeasure (run
  `blocked-catalog-rt5e-iteme`, on the branch): zero delta vs
  `blocked-catalog-019-field`.
- Clean-room: no CE inputs touched; the corpus is read-only (the
  remeasure never modifies it); the new analysis doc cites the CE 7.5
  tree read-only with file:line evidence.

The 0.21 build was cut from this content set via
`scripts/Build-Native.ps1` as run `native-20261031T211046Z-14707e12`
from `main` @ `9a725a8` (2026-10-31; in-build suite 4,044 OK / 30
expected skips, fully green at the canonical path - the full build
record is in the 0.21 Master Trainer ledger section below).

### 0.21 Master Trainer (2026-10-31, released in build `native-20261031T211046Z-14707e12`)

User request (2026-10-31): a "Forever Master Trainer" — one long-lived
trainer window configured with a folder of `.ct` tables. It indexes
every table in that folder (sub-folders included) together with the
process names each table can bind to — incrementally, so only the
folder listing is done per reconcile and only changed files are
re-read — then waits for a matching game process. A unique
table-for-process match auto-loads; when several tables bind one
process the user picks in the UI. The window then switches into the
exact standalone trainer UI, and per-table on/off configuration is
persisted and restored on the next load of the same table. No new
CE/trainer functionality: the existing tested engine and UI are reused
unchanged; the scope is trainer/cheat handling and game-facing effects
only. Platform independent: Windows (Toolhelp32) and Linux/SteamOS
(`/proc/<pid>/exe`) process watching, for later CheatDeck use.
Developed in parallel via subagent lanes (core + UI test lanes) and
closed by the root integrator.

Implementation (branch `native-0.20-master-trainer`: `0b12316`
feature, `05e1943` test-lane closure + source fixes; merged `main`
first at `322ae22` (`c833667`), final merge commit `9a725a8`;
icon-test fix `7360f82`; changelog suite line `01c3d36`):

- New `ct2trainer.native.master_trainer` package (`CONCEPT.md` +
  `ROADMAP.md` in-package):
  - `table_index.py` — incremental folder index: per reconcile only a
    directory listing is done; an entry is re-read only when its
    `(size, mtime_ns)` fingerprint changed; a content-identical
    (sha256-equal) refresh keeps the derived process names without
    re-parsing; removed paths drop; unreadable tables stay visible with
    a named error and bind no process. Canonical JSON persistence with
    a sha256 checksum bound to the root — foreign schema, foreign root
    and tampered checksums are refused; a missing root keeps the
    stored entries and records a scan error. The index lives in the
    state home (`tables-index.json`), never in the table folder.
  - `process_watch.py` — read-only process snapshots: Toolhelp32 on
    Windows, `/proc/<pid>/exe` on Linux/SteamOS (Proton-compatible);
    pure, deterministic matcher (ordinal case-insensitive for ASCII,
    casefold otherwise).
  - `orchestrator.py` — waiting → choosing → loading → active state
    machine, pure and UI-free: unique-match auto-load (silent),
    multi-table picker contract, deterministic first-casefold-sorted
    name / lowest-PID rule, fail-closed loop guard (failed and
    deferred exact (name, PID) pairs; PID-gone re-arm; explicit retry
    re-arms), open-choice stability (a picker already open receives no
    other load request; a stale choice drops back to waiting).
  - `master_ui.py` — waiting view (folder line, index Treeview, status
    line, Rescan / Change folder / Retry load), modal table picker with
    "Not now" deferral (suppression of the exact (name, PID) pair
    until exit), and the trainer handoff with the same
    startup-recovery flow as the standalone trainer (stale state,
    orphaned receipts, live conflict, bounded non-convergence).
- `TrainerWindow` gained an optional `master_back` callback: one extra
  "⬅ Master" header button that closes the engine cleanly (with the
  unclean-close warning) and rebuilds the waiting view on the same Tk
  root; `None` keeps the standalone trainer byte-identical
  (`ui.py` master_back + render guard).
- Per-table on/off persistence: the same engine state store as the
  standalone trainer (same table + process + arch → same state
  directory), so saved toggles restore on the next load of the same
  table; the `settings_model.py` sidecar wiring is queued (MT-6).
- CLI: `ct2trainer native master [FOLDER]` (`--state-dir`,
  `--debug-log`, `--poll-ms`); directory picker when the folder
  argument is omitted.
- Build allowlist (`tools/native_build.py`): the `master_trainer`
  subpackage (code + in-package docs) and the user-provided
  `Master_Trainer.ico` / `Master_Trainer.png` ship in the source ZIP;
  `window_icon_path("master")` resolves the master window icon.

Four source bugs found and fixed during test-lane development:

1. `process_watch.py`: `from ..local_processes` → `from
   ...local_processes` (the module lives at
   `ct2trainer.local_processes`; the Windows backend raised
   `ModuleNotFoundError` on first tick).
2. `master_ui.py` `_open_picker`: `pady=(12, 4)` / `pady=(4, 12)`
   moved from Tk widget options to `.pack()` (tuple padding is only
   valid as a pack/grid option; the picker crashed with
   `TclError: bad screen distance` every time it opened).
3. `master_ui.py` `_confirm_recovery`: a declined recovery prompt now
   fails the load instead of returning `True` (which re-prompted up to
   4 times then stranded the orchestrator in `STATE_LOADING`; the
   standalone trainer exits on decline).
4. `master_ui.py`: the `_enter_trainer` non-convergence path now fails
   the load via `_fail_trainer_start` (returns to `STATE_WAITING` and
   arms the loop guard), and `set_folder` gained the missing
   `TableIndex` import (was a `NameError` on every "Change folder"
   click).

Tests: `tests/test_native_master_index.py` (18),
`tests/test_native_master_process_watch.py` (35; Lane A's file,
self-skip removed with the import fix, asserts `pid >= 0` because the
Toolhelp snapshot includes PID 0), `tests/test_native_master_ui.py`
(46; Lane A's core file plus the valuable Lane B edge-case ports;
Lane B's three "observed bug" pins are superseded by the fixes above),
`tests/test_native_icons.py` updated for the third icon kind (master
is now a valid `window_icon_path` kind; the unknown-kind probe moved to
"no-such-kind"). 141 master-trainer tests total.

Full dev suite on the merged branch (worktree run, 2026-10-31): 4,044
run, **4,011 OK / 30 expected skips**; the only 3 failures are the
known path-dependent baseline-reproducibility tests
(`test_native_repro_chain.py`), whose committed baselines embed the
canonical repo path — they fail in any other worktree and pass at the
canonical build path. Baseline math: `main` @ `322ae22` = 3,902
(3,876 + RT-5 B's +26); merged branch = 3,902 + 141 master tests + 1
new icon test = 4,044.

Catalog: unchanged vs `blocked-catalog-020-icons` (the feature touches
no plan-builder code; consistent with the asset/UI-only precedent of
the 0.20/0.20.1 cycles).

Build (2026-10-31, canonical path, `scripts/Build-Native.ps1`): run
`native-20261031T211046Z-14707e12` from `main` @ `9a725a8` - in-build
suite **4,044 OK / 30 expected skips, 0 failures** (fully green,
incl. the 3 path-dependent baseline-reproducibility tests),
`ce_inputs: []`, `runtime_unverified` deliberately kept per gate;
`CT2Trainer-0.21-source.zip` sha256
`9dacb4093cd8a7f0444fed9ed7ae9aed6f82c14132ee4f3197b1fb5747580a13`
(14,231,850 bytes) - carries the `master_trainer` subpackage, all 4
master test files and both `Master_Trainer` icon assets - and
`CT2Trainer-0.21-windows-portable.zip` sha256
`0701d507701cb2952e1e35e1357bac4b459b38fe87e6811b6b272f2a2c3acaaa`
(33,010,077 bytes).

Open items carried: user field test of the Master Trainer window;
MT-6/7/8 queued (`settings_model.py` sidecar wiring, SteamOS/CheatDeck
attach route, frozen `CT2Trainer-Master.exe` entry point); clean
Windows and real Steam Deck/Proton/touch acceptance remain open;
`runtime_unverified` deliberately kept per gate.

### 0.24 content: trainer tick sounds (2026-11-01, branch `native-0.24-trainer-sounds`)

User field request (sent repeatedly on 2026-11-01): "make sure that
the resulting trainer uses the sounds of the original native trainer
generator - so toggle sounds for successful attach, and manual toggle
of item on/off". Behavior reference (read-only, never copied): the CE
7.5 native trainer generator plays two built-in tick sounds on cheat
toggle - `Sounds.RC` registers `tick1.wav` / `tick2.wav` as the
`BUILDIN_ACTIVATE` / `BUILDIN_DEACTIVATE` RCDATA resources, measured
~28 ms, 8-bit unsigned mono, 11025 Hz, high-pitch square-wave ticks
(~4.4 kHz activate / ~3.8 kHz deactivate), played through the Win32
winmm `PlaySound` API as memory buffers (`SND_MEMORY | SND_ASYNC`,
non-Windows no-op). The reference-corpus tables carry no
table-embedded audio files (only PNGs), so that built-in pair is the
original sound set. Clean-room decision: the ticks are synthesized
deterministically in code in the same format and pitch character -
no CE asset bytes enter the repository or the generated trainer.

Implementation (root, directly on `main`):

- **`src/ct2trainer/native/trainer_sounds.py` (new):** deterministic
  synthesis of the three ticks as 8-bit unsigned mono 11025 Hz
  RIFF/WAVE bytes (on: 5512.5 Hz / 28 ms; off: 3675 Hz / 28 ms;
  attach: a distinct double 3675 Hz tick with a silent gap - silence
  is explicit 128 bytes in 8-bit unsigned PCM); module-cached buffers
  (`SND_MEMORY` requires the buffer to stay alive for the playback);
  `play_sound(kind)` is best-effort - Win32 winmm `PlaySound` with
  `SND_MEMORY | SND_ASYNC`, a stable named result string
  (`played` / `skipped: non-windows platform` / `refused:
  <reason>`), and never raises into the UI.
- **`ui.py`:** the old 880/440 Hz sine `play_toggle_sound` helper
  (WP-58) is removed; the row switch and the group heading toggle
  both play the tick for the resulting state (CE parity: the
  generated trainer sounds on every toggle, not only switch taps),
  and `TrainerWindow.poll()` detects the attach-success transition
  (engine memory handle going from nothing to a live target) and
  plays the attach tick exactly once per (re-)attach - failed attach
  attempts leave the handle None and stay silent. The poll tick also
  pops the engine's hotkey-toggle list and plays the same on/off
  tick a manual tap would (the OS hotkey bridge dispatches through
  the engine, not the UI).
- **`engine.py`:** confirmed activation toggles dispatched through
  the hotkey path (OS bridge drain or programmatic
  `dispatch_hotkey`) are recorded as `(record_id,
  resulting-active)` pairs and surfaced through
  `TrainerEngine.pop_hotkey_ui_toggles()` (append-only between pops;
  headless consumers never pop). Value-action hotkeys are not
  recorded (no activation state change).

Evidence: focused `test_native_trainer_sounds` 21/21; `tests/test
_native_ui_tone.py` (4 tests on the removed helper) superseded and
removed; full main suite 4,193 OK / 30 expected skips (4,176 - 4 +
21); catalog remeasure `blocked-catalog-024-sounds` (2026-11-02):
zero delta vs `blocked-catalog-023-field-fixes` (151/151 loaded, 0
compile errors, 117,809 total / 116,756 supported / 60,161 staged /
1,053 blocked / 0 load errors; per-table changes 0). VERSION bumped
to 0.24 with the changelog entry in the same change (versioning
rule). Build `native-20261102T102029Z-fe358e35` (2026-11-02, cut
from `main` @ `a2777ed`): in-build suite 4,193 OK / 30 expected
skips (status passed), `ce_inputs: []`, `runtime_unverified`
deliberately kept per gate; source ZIP `CT2Trainer-0.24-source.zip`
sha256 `dfdd8cfcca90a2789bf544d8f8de4e34941067feeb2b32ce8d550f98e5bc4eb6`
(14,298,696 bytes), portable ZIP
`CT2Trainer-0.24-windows-portable.zip` sha256
`12262cf16e906c3811ade0a8c582b7a1057c834a3110aff004dfd13b3067e7ab`
(49,618,009 bytes); frozen `CT2Trainer-Master.exe` (sha256
`5f3a66400c2c1775e6fc50ad6bbbc36aa8a6bcf8b58fe56507117dc33683494d`,
16,896,995 bytes) in the run folder, the payload inventory and the
portable ZIP. The tick sounds are untested on a live game session
(field test pending).

### 0.25 content: Master Trainer user control MT-10/11/12 (2026-11-02, root-direct on `main`)

User request (2026-11-02): give the user explicit control over which
table loads and which process attaches, plus detach / re-attach on
demand. The feature set was evaluated against online all-in-one
trainer front ends (OpenForge (openforge-aio), the CE 7.5 process
picker as a local read-only behavior reference, LaunchForge /
auto-update loaders); the evaluation is recorded in
`src/ct2trainer/native/master_trainer/ROADMAP.md` ("Online feature
evaluation (2026-11-02)"). Adopted: MT-10/11/12. Deliberately
deferred (documented): global per-feature hotkeys, auto-update
(offline/hash-verified build policy) and concurrent multi-table
sessions (documented single-session model).

- **MT-10 (explicit table load):** a "Load table" header button in
  the waiting view plus a per-row "Load this table" context menu.
  The table loads even while the bound process is not running yet
  (the plan compiles statically; the engine waits for the process to
  start). The last explicitly loaded table persists in the state
  home (`master-settings.json` schema 2, `last_table`) and is visible
  in the metadata line. `orchestrator.request_load()` carries stable
  named refusals (`not-in-index` / `table-unreadable` /
  `no-process-binding` / `process-snapshot-failed`): a refused load
  shows a named dialog + status line, never a crash; an explicit
  load bypasses the auto-load loop guard, but a failed explicit load
  still records the ordinary (name, PID) suppression.
- **MT-11 (process selection + persisted attach mode):** new
  `process_picker.py` (pure decision layer: `candidate_processes`,
  `attach_decision` -> attach-direct / pick / wait,
  `make_pinned_memory_factory` - the injected factory honors the
  session PID pin, self-clears the pin once that PID exits, falls
  back to the ordinary smallest-PID name-based attach). Attach
  modes: "auto" (default, legacy behavior - no picker, smallest PID)
  and "ask" (the process picker, one row per running candidate
  name + PID, is shown for every attach, even a single candidate).
  The "Attach: auto/ask" toggle button persists the mode
  (`master-settings.json` schema 2; schema-1 documents promote on
  load with the documented defaults `last_table=null`,
  `attach_mode="auto"`). Cancel semantics per origin: an auto-load
  pick defers the exact (name, PID) pair (Retry load re-arms), a
  table choice defers exactly like "Not now", an explicit load
  returns to the waiting status, an attach after detach stays
  paused.
- **MT-12 (detach / user attach):** engine `pause_attach()` /
  `resume_attach()` / `attach_paused` - while paused the poll attach
  branch is gated (status "Detached; waiting for user attach", no
  attach attempts, session state/journals/wishes untouched; debug
  events `attach-paused` / `attach-resumed`; pausing refused with a
  named error while closed/blocked/busy). The new "Detach"/"Attach"
  header button exists in Master mode only - the standalone trainer
  header stays byte-identical (`TrainerWindow` gains the optional
  `detach_cb`). On "Attach": "ask" mode with running candidates
  opens the process picker (origin "attach") and the chosen PID pins
  the session, then the hold resumes; "auto" mode simply resumes the
  ordinary wait; a target exit while attached is unaffected.

Test-harness hardening (test-only change, no product code change):
new `tests/native_tk_teardown.py` with `force_root_release()` -
deterministic Tk-root teardown on the creator thread (destroy + drop
named test-side references + forced main-thread `gc.collect`)
applied in all 7 UI test modules (17 root creations:
`test_native_master_ui.py`, `test_native_master_ui_mt12.py`,
`test_native_sc2_crash_observability.py`,
`test_native_staged_options_ui.py`, `test_native_trainer_sounds.py`,
`test_native_ui_button.py`, `test_native_ui_row_details.py`). It
removes the intermittent `Tcl_AsyncDelete: async handler deleted by
the wrong thread` abort observed in the 0.25 full-suite non-verbose
runs (2026-11-02). Mechanism (verified against the CPython 3.12
tkinter source + faulthandler dump): `Tk.destroy()` destroys the
toplevel window and deletes the widgets' Tcl commands, but the
underlying Tcl interpreter (the `_tkinter` Tkapp behind `root.tk`)
is only released when the Python Tk object is deallocated; the
root/interpreter reference cycle (the `after` poll callback and
button commands hold bound methods inside the interpreter; the
bound methods hold the window; the children/master bookkeeping holds
the root) survives until the next cyclic GC, which runs on whatever
thread allocates; when a worker thread's GC cycle finalizes the
interpreter, Tcl aborts the process off the creator thread. The
fault dump showed the fatal thread as a freshly started thread
running the GC collector while the main test thread was mid NASM
assembly in `test_native_record_hotkeys`. Evidence: two full-suite
non-verbose runs aborted with the Tcl fatal (exit 1, no summary,
~71% position); the verbose full run completed green (Ran 4258, OK,
skipped=30); a middle-set repro (`test_native_master_ui` +
`test_native_master_ui_mt12` + `test_native_os_hotkeys` +
`test_native_rearm` + `test_native_record_hotkeys`, x10) did not
reproduce; a clean-tree (0.24 @ `aba8b65`) full run completed
without the Tcl fatal.

In-build reliability fix: the first 0.25 in-build suite run
(`native-20261102T181843Z-ddfb63f0`, 2026-11-02; 4,259 ran, 1 error,
the rest green) exposed a state-home dependence the isolated local
dev runs never hit - the in-build suite runs without the LOCALAPPDATA
isolation, so the `run_master` cancel test read the machine's real
state home and, on a field-tested box with a stored `last_folder`,
took the stored-folder reuse path with the mocked `tk.Tk` and failed
at the waiting-view status variable. The test now uses an isolated
state home, a new deterministic test covers the stored-folder reuse
path, and the waiting-view status variable plus the table-picker
selection variable in `master_ui.py` carry an explicit master (the
window root) instead of relying on the tkinter default-root lifecycle.

Evidence: +66 tests (`tests/test_native_master_process_picker.py`
16, `tests/test_native_master_explicit_load.py` 13,
`tests/test_native_attach_pause.py` 5,
`tests/test_native_master_ui_mt12.py` 24, +7 schema-2 tests in
`tests/test_native_master_state.py`, +1 state-home isolation test in
`tests/test_native_master_ui.py`); full main suite **4,259 OK /
30 expected skips** (2026-11-02); catalog remeasure
`blocked-catalog-025-master-ui` (chunked 64x3 audit over the 151
reference tables, 2026-11-02): 151/151 loaded, 0 load errors,
117,809 total / 116,756 supported / 60,161 staged / 103,607
actionable / 12,974 headings / 1,053 blocked - **zero delta** vs
`blocked-catalog-024-sounds` (per-table count/reason/sha changes:
0). Feature matrix unchanged (42/42, 7,475/7,475 over
`w4b4-case30-20261020081722Z`); AP-11 0/6,143. VERSION bumped to
0.25 with the changelog entry in the same change (versioning rule).
The 0.25 build `native-20261103T062439Z-f4c16be9` was cut from
`main` @ `a861bfb` (2026-11-03): in-build suite 4,259 OK / 30
expected skips, `ce_inputs: []`, `runtime_unverified` deliberately
kept per gate; source ZIP `CT2Trainer-0.25-source.zip` sha256
`64f8c3082cff50687b1962234c17a82e2a2f0c19eb1112ece06a0a25132f35be`
(14,324,774 bytes), portable ZIP
`CT2Trainer-0.25-windows-portable.zip` sha256
`774266f7e2c9dc69f4d8cfc963309b9907442ec6b5343ff629b9e30c04049653`
(49,633,196 bytes; the frozen `CT2Trainer-Master.exe` sha256
`8736f73e762b57a8f337bf8fa04c2c16f8622c4d99e7dd7f2167b2c9999e3d8f`,
16,912,561 bytes, ships next to the converter).

### 0.30 content: Master Trainer table details + live load-gate preview (MT-22) (2026-11-04, root-direct on `main`)

0.30 bundles the table-details inspection of the Master Trainer
waiting view (the adopted 0.30 candidate from the online evaluation
recorded in `master_trainer/ROADMAP.md`, the "0.30 table details +
load-gate preview" section - FLiNG per-trainer version / "Last
Updated" metadata, game-trainer-manager organize/search workflows,
Game Cheats Manager .ct handling FAQ, Cheat Happens Trainer Manager
v2 portable + last-used pinning). Adopted: MT-22. Deliberately
deferred (documented, unchanged candidates): the MT-21 multi-column
trainer grid, the entry-count / blocked-count columns and the
per-table status / color-coding.
- **MT-22 table details + live load-gate preview:** right-clicking a
  waiting-view row offers "Table details" first - a read-only
  Toplevel (title "Table details - <rel>", transient to the root,
  non-resizable, Close button) with the indexed facts for the
  table: path, folder, size, modified, bound processes, index
  status (ok / unreadable: <reason>), pin state, last used (the
  persisted UTC timestamp or "never"), running PIDs (deduped,
  sorted, "not running" when none), content sha256 (last scan -
  first 12 hex + "...") - plus the on-demand `gate_table_for_load`
  re-check: the same pass MT-9 runs at load time, so a refusal
  shows the stable named code + displayable detail (a stale /
  changed / unreadable table is explained at inspection time, not
  only at load time); a passing gate proves the file matches the
  last scan. One window (a second open lifts + focuses the open
  window instead of duplicating); closed on trainer entry with the
  rest of the waiting view; no index entry leaves a named status
  line instead of a window. The row builder is pure in
  `master_trainer/table_details.py` (`format_size` / `format_mtime`
  / `gate_line` - "not checked" / "OK (loadable - the file matches
  the last scan)" / "<code>: <detail>", named fallbacks;
  `table_detail_lines` - the 11 ordered (label, value) rows); the
  only I/O is the bounded gate re-check under the load limit. The
  in-app `ui_flow_text()` and the reviewable
  `master_trainer/UI.md` document the new row-menu entry (keyboard
  map + table-tree section).
- +16 tests (`tests/test_native_master_ui_mt22.py` new: the pure
  builder - all facts in order, the unreadable entry + named
  fallbacks, the no-bound-processes label, the deduped/sorted PIDs,
  the size / mtime / gate-line formatters with boundaries; the Tk
  wiring - the menu order through a recording `tk.Menu` subclass,
  the details command opening the window for the row, the indexed
  facts incl. the live "OK (loadable...)" gate line, lift on second
  open, trainer-entry close, the named refusal display, the
  last-used timestamp).
- Full main suite 4,386 OK / 30 expected skips (4,370 from the
  0.29 content + 16 new MT-22 tests); catalog remeasure
  `blocked-catalog-030-details` (chunked 64x3 audit over the
  151 reference tables, 2026-11-04): 151/151 loaded, 0 load errors,
  117,809 total / 116,756 supported / 60,161 staged / 103,607
  actionable / 12,974 headings / 1,053 blocked - **zero delta** vs
  `blocked-catalog-029-trainer-focus` (per-table count/reason/sha
  changes: 0); feature matrix unchanged (42/42, 7,475/7,475 over
  `w4b4-case30-20261020081722Z`); AP-11 0/6,143. VERSION bumped to
  0.30 with the changelog entry in the same change. The 0.30
  build `native-20261104T131114Z-11522f68` was cut from `main` @
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

### 0.29 content: Master Trainer UI/UX revamp (MT-19/20) (2026-11-04, root-direct on `main`)

0.29 bundles the UI/UX revamp of the Master Trainer (the user field
request of 2026-11-04: when a process is identified and the trainer
attaches, the waiting table list must shrink/collapse so the
trainer items get maximum space; the UI should be generally more
accessible; and the UI flow should be documented so it can be
reviewed and improved). The request was evaluated against the local
shared-root trainer handoff (the root cause: the waiting-view
widgets are packed directly on the shared root and are never
destroyed on trainer entry, so the table list keeps sharing the
window with the trainer rows) plus the standing trainer-manager UI
evaluations (Trinity "hotkeys, profiles" - saved per-game
configurations, corroborated by the standing user requirement "merkt
sich das einmal eingestellte", already covered by
MT-6/11/15/16/18; Cheat Happens AURORA "easily accessible for the
games you are currently playing" - discoverability; the keyboard-
shortcut databases - a documented shortcut map is a recognized
app-UX baseline; the WCAG / platform accessibility guidance -
descriptive labels, keyboard operability, no reliance on a single
input path; see the Master Trainer ROADMAP "0.29 trainer-focus +
discoverability" section). Adopted: MT-19, MT-20. Deliberately
deferred (documented candidate MT-21, separate cycle): the multi-
column trainer grid - the single-column canvas grid is the
validated touch-first design (`ui_rows.py` pure row model +
`ui_layout.py` + the 1-D hit-testing, exhaustively tested and
shared with the standalone trainer); a column layout rewrites the
pure row model, the pagination and the 2-D hit-testing and changes
the standalone trainer as well.
- **MT-19 trainer-focus mode:** the whole waiting view now lives in
  one container frame (`MasterWindow._waiting_frame`,
  `fill=both expand=True` on the shared root) - the header
  (title, filter, sort/view cycles, repo link, Load table / Change
  folder / Rescan / UI flow / Close), the folder/meta/running
  lines, the table-tree frame and the status bar are all its
  children. `_enter_trainer()` destroys the container immediately
  after the engine is up (before the `TrainerWindow` is built) and
  drops every waiting-view widget reference, so the trainer row
  grid owns the full window instead of sharing it with the table
  list, and the poll loop / handlers never touch a destroyed
  widget (the poll tick already early-returns in trainer mode). The
  trainer-constructor failure path rebuilds the waiting view before
  `_fail_trainer_start()` so the waiting loop and its loop guard
  stay consistent; `_back_to_master()` is unchanged (destroy-all +
  rebuild). The open UI-flow Toplevel is closed with the teardown.
- **MT-20 discoverability:** the module function `ui_flow_text()`
  (headless-testable) is the plain-language UI-flow document - the
  same content as the reviewable `master_trainer/UI.md` in the
  package (ships in the source ZIP through the existing `.md`
  allowlist in `tools/native_build.py`); the new "UI flow" header
  button opens it in a read-only Toplevel (single window: a second
  click lifts + focuses the open window instead of duplicating; the
  window is transient to the root and closed on trainer entry). F5
  re-scans the folder from anywhere in the waiting view (root
  binding, guarded no-op in trainer mode exactly like the existing
  "/" binding). The table tree takes the initial focus on build
  (`focus_set` at the end of `_build_waiting_view`), so arrow keys
  and Enter work immediately without a first click. The "Retry
  load" re-arm moves out of the root-level button below the status
  strip into the status bar next to the attach toggle and the
  Recent button.
- +13 tests (`tests/test_native_master_ui_mt19.py` new: container
  parenting, the collapse through the patched handoff, the
  constructor-failure rebuild, the back-to-master fresh frame, one
  real-`TrainerWindow` case, the flow-document content, the
  read-only Toplevel + lift-on-second-click, the trainer-entry
  close, the F5 contract in both modes, the initial-focus spy, the
  retry-bar placement).
- Full main suite 4,370 OK / 30 expected skips (4,357 from the
  0.28 content + 13 new MT-19/20 tests); catalog remeasure
  `blocked-catalog-029-trainer-focus` (chunked 64x3 audit over the
  151 reference tables, 2026-11-04): 151/151 loaded, 0 load errors,
  117,809 total / 116,756 supported / 60,161 staged / 103,607
  actionable / 12,974 headings / 1,053 blocked - **zero delta** vs
  `blocked-catalog-028-pin` (per-table count/reason/sha changes:
  0); feature matrix unchanged (42/42, 7,475/7,475 over
  `w4b4-case30-20261020081722Z`); AP-11 0/6,143. VERSION bumped to
  0.29 with the changelog entry in the same change. The 0.29
  build `native-20261104T094808Z-50af0517` was cut from `main` @
  `de3e4ff` (2026-11-04): in-build suite 4,370 OK / 30 expected
  skips, `ce_inputs: []`, `runtime_unverified` deliberately kept
  per gate; source ZIP `CT2Trainer-0.29-source.zip` sha256
  `2f5ce6e446f8d9885cd653580b5e194a2a0fc524eba7b5f684fe1f1a0e1da3d4`
  (14,378,934 bytes), portable ZIP
  `CT2Trainer-0.29-windows-portable.zip` sha256
  `98c63c368bc2cccd68335e9db94a3b897abbbb815730c97912e3068805fad226`
  (49,667,528 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `88e6ee99aa4c46973945e462ca956977e9942a1e8b30630aa2570107540f2de8`,
  16,937,063 bytes, ships next to the converter).

### 0.28 content: Master Trainer pinned/favorite tables (MT-18) (2026-11-03, root-direct on `main`)

0.28 bundles the pinned/favorite tables feature for the Master
Trainer (the adopted 0.28 candidate from the 0.27 follow-up online
evaluation recorded in `master_trainer/ROADMAP.md` - VGC Shelf
("sort, pin, archive"): pinning as a first-class feature; with
~151 indexed tables the ones the user touches daily deserve a
permanent place at the top). Deliberately deferred (documented):
entry-count / blocked-count columns (the catalog numbers belong to
the local tooling, not the waiting view) and per-table status /
color-coding (the indexed Status column plus the running-PID
markers already carry the state; a status taxonomy would be a
feature in its own right).
- **MT-18 pinned / favorite tables:**
  `master-settings.json` schema 4 -> 5: `pinned_tables` (relative
  table paths, most recent pin first, capped at
  `PINNED_TABLES_LIMIT` = 25, each a non-empty string within the
  `_MAX_TABLE_PATH` bound). Schema-4 documents promote on load
  with `pinned_tables=[]`; a schema-4 document carrying the field
  is refused as an unknown field (foreign schema, never silently
  promoted - the same discipline as MT-11/15/16). The pure
  `table_filter.pin_tables` reshaping of the already-sorted-and-
  filtered row set (never adds or drops tables): pinned rows first
  in pin order (casefolded comparison, a duplicated pin path never
  duplicates the row), the remainder keeps the input order, pin
  paths not in the row set (filtered out or gone) ignored. UI: the
  row context menu gains "Pin to top" / "Unpin"
  (`_toggle_table_pin` -> `MasterApp.set_table_pinned`, named
  `ValueError`s for cap / already pinned / not pinned, immediate
  persist through `persist_state`); `MasterApp.is_table_pinned`
  (casefolded) feeds both the menu label and the marker; a pinned
  table floats to the top of the list view and to the top of its
  process group in the grouped view (the pin set is applied after
  filter + sort, before the MT-17 grouping); the pin marker lives
  in the detail column ("pinned" / "pinned - PID ..."), the first
  column stays the bare relative path (the row identity
  `_table_selected_rel`, the double-click and the load paths key
  off); a named refusal lands in the status line without a state
  change or a crash. +15 tests
  (`tests/test_native_master_state.py` +4,
  `tests/test_native_master_table_filter.py` +4,
  `tests/test_native_master_ui_mt18.py` new +7).
- Full main suite 4,357 OK / 30 expected skips (4,342 from the
  0.27 content + 15 new MT-18 tests); catalog remeasure
  `blocked-catalog-028-pin` (chunked 64x3 audit over the 151
  reference tables, 2026-11-03): 151/151 loaded, 0 load errors,
  117,809 total / 116,756 supported / 60,161 staged / 103,607
  actionable / 12,974 headings / 1,053 blocked - **zero delta** vs
  `blocked-catalog-027-view` (per-table count/reason/sha changes:
  0); feature matrix unchanged (42/42, 7,475/7,475 over
  `w4b4-case30-20261020081722Z`); AP-11 0/6,143. VERSION bumped to
  0.28 with the changelog entry in the same change. The 0.28
  build `native-20261103T161621Z-ea8fde2f` was cut from `main` @
  `d7f4cf0` (2026-11-03): in-build suite 4,357 OK / 30 expected
  skips, `ce_inputs: []`, `runtime_unverified` deliberately kept
  per gate; source ZIP `CT2Trainer-0.28-source.zip` sha256
  `13f4b2222a83f9e4588d388b4120beaf8018a091a05364029ae2a950c0dabb1a`
  (14,363,765 bytes), portable ZIP
  `CT2Trainer-0.28-windows-portable.zip` sha256
  `d656835a69ece75ff6adaa5ce766385327fb9ec08d89837ad772425dafe91ce3`
  (49,658,473 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `c12dcea5bb8a609dae4df36f44827ab5269c9e1015cb723067ed98dc100bf99b`,
  16,929,732 bytes, ships next to the converter).

### 0.27 content: Master Trainer waiting-view settings persistence (MT-16) + process-grouped waiting view (MT-17) (2026-11-03, root-direct on `main`)

0.27 bundles the waiting-view settings package for the Master
Trainer (follow-up online evaluation recorded in
`master_trainer/ROADMAP.md`, "0.27 waiting-view settings +
process groups" - playR ("ratings, lists, statuses, filters,
sorting and statistics"), Universal Game Launcher ("powerful
filters and bookmarks"), GamesList Manager ("sortable columns,
color-coded status, search"), Game Cheats Manager; the standing
user requirement that the waiting view is configurable and
remembers what was set once; both items deliberately deferred in
0.26 are adopted). Deliberately deferred (documented):
entry-count / blocked-count columns (the catalog numbers belong
to the local tooling, not the waiting view) and per-table status
/ color-coding (the indexed Status column plus the running-PID
markers already carry the state; a status taxonomy would be a
feature in its own right).
- **MT-16 persisted waiting-view settings:**
  `master-settings.json` schema 3 -> 4: `view_filter` (the raw
  filter entry text, at most `VIEW_FILTER_MAX` = 200 characters,
  "" = no filter), `view_sort` (one of the table_filter sort
  modes, mirroring `table_filter.SORT_MODES`) and `view_mode`
  ("list" flat rows / "process" grouped by bound process name,
  mirroring `table_filter.VIEW_MODES`). Schema-1/2/3 documents
  promote on load with the documented defaults ("" / "name" /
  "list"); a schema-3 document carrying a view_* field is
  refused as an unknown field (foreign schema, never silently
  promoted - the same discipline as MT-11/MT-15). The
  format-level constants live in `master_state` (the
  attach-mode pattern); a test pins the mirror against the pure
  layer. `MasterApp.set_view_settings(filter_query, sort_mode,
  view_mode)` validates with named `ValueError`s (unknown sort /
  view mode, non-string or over-long filter) and re-persists
  immediately; the window restores all three from the persisted
  document at construction; every UI change point re-persists
  (filter `<KeyRelease>`, sort cycle, view cycle, Esc clear).
  +4 state tests (`tests/test_native_master_state.py`) + 5 UI
  tests (`tests/test_native_master_ui_mt16.py`).
- **MT-17 process-grouped waiting view:** the pure
  `table_filter.group_tables_by_process` reshaping of the
  already-sorted-and-filtered row set (never adds or drops
  tables): one parent row per casefolded bound process name (a
  table bound to several names appears once under EACH of them),
  the tables without a bound name under `UNBOUND_PROCESS_LABEL`
  ("(no process binding)") last, bound groups casefolded-sorted,
  within-group order = the caller's sort order. The "View:
  list/process" cycle button sits between the sort button and the
  filter entry (persisted through MT-16); the tree
  (`show="headings"`) renders the group label + "N table(s)"
  count into values[0] of the parent row (the text item is
  invisible with headings); the children through
  `_insert_table_row`. Group rows are display-only -
  `_is_table_row` (parent exists, or top-level in the flat
  view) gates the double-click, the Enter selection
  (`_table_selected_rel`) and the row context menu, so a group
  row never loads; the children load through the ordinary MT-10
  path. +8 pure tests
  (`tests/test_native_master_table_filter.py`) + 5 UI tests
  (`tests/test_native_master_ui_mt16.py`).
- Full main suite 4,342 OK / 30 expected skips (4,320 from the
  0.26 content + 22 new MT-16/17 tests); catalog remeasure
  `blocked-catalog-027-view` (chunked 64x3 audit over the 151
  reference tables, 2026-11-03): 151/151 loaded, 0 load errors,
  117,809 total / 116,756 supported / 60,161 staged / 103,607
  actionable / 12,974 headings / 1,053 blocked - zero delta vs
  `blocked-catalog-026-master-ui` (per-table count/reason/sha
  changes: 0); feature matrix unchanged (42/42, 7,475/7,475 over
  `w4b4-case30-20261020081722Z`); AP-11 0/6,143. VERSION bumped
  to 0.27 with the changelog entry in the same change. The 0.27
  build `native-20261103T145543Z-b29b3688` was cut from `main` @
  `8aa0815` (2026-11-03): in-build suite 4,342 OK / 30 expected
  skips, `ce_inputs: []`, `runtime_unverified` deliberately kept
  per gate; source ZIP `CT2Trainer-0.27-source.zip` sha256
  `264b42d6c42dac1bb434c1d0591e82ac0bec69e61e1a1c75047c6aa58126f40e`
  (14,357,294 bytes), portable ZIP
  `CT2Trainer-0.27-windows-portable.zip` sha256
  `bfcf2abc885122dfa8653fcfd0046323e7112f59c0850958688e36e014ebc135`
  (49,654,613 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `9762c8bdc2298c16bd82779f206d9a885a449261a6428187c3bd2155fc5bf1bc`,
  16,929,639 bytes, ships next to the converter).

### 0.26 content: Master Trainer waiting-view usability MT-13/14/15 + live-target takeover field fix (2026-11-03, root-direct on `main`)

0.26 bundles the waiting-view usability package for the Master
Trainer (user request 2026-11-02/03; feature evaluation recorded
in `master_trainer/ROADMAP.md`, "0.26 waiting-view usability")
with the live-target takeover field fix that already shipped on
`main` (commit `3ffa8fa`; field case 2026-11-03, Indiana Jones
0.22 log: the hotkey-bridge AV left `state.lock` while the game
kept running, so the strict all-dead recovery proof could never
pass and only a manual state-folder delete worked). Adopted:
MT-13/14/15. Deliberately deferred (documented): group-by-process
tree, persisted filter/sort, entry-count / blocked-count columns.
- **MT-13 search / filter / sort:** new pure decision layer
  `table_filter.py` (no OS / index / state access):
  `filter_tables` (empty/whitespace query = the identity, input
  order preserved; otherwise a casefolded substring over the
  table's relative path AND any bound process name - a table
  matches when ANY bound name matches) and `sort_tables` (modes
  name / process / status; the casefolded relative path is the
  universal tie-breaker; in process mode unbound tables sort last;
  unknown mode raises `ValueError` - named refusal). The waiting
  view renders `filter_tables(sort_tables(index.tables(), mode),
  query)`; row identity stays the relative path; the load picker
  and the auto-load path keep the full index. Filter and sort are
  session-only: they survive the trainer round-trip but are never
  persisted. Header filter entry (live re-render; meta line shows
  `filtered: N/M`) + "Sort: name/process/status" cycle button.
  +17 pure tests (`test_native_master_table_filter.py`) + 4 UI
  tests in `test_native_master_ui_mt13.py`.
- **MT-14 keyboard flow:** double-click, Return and KP_Enter load
  the selected row through the MT-10 explicit-load path (named
  refusals included, no new load logic); arrow keys are built into
  the Treeview; "/" focuses the filter from anywhere in the
  waiting view (a no-op in trainer mode); Esc on the filter clears
  it and returns focus to the table list. +3 tests in
  `test_native_master_ui_mt13.py`.
- **MT-15 recent tables + Size / Modified / Last-used columns:**
  `master-settings.json` schema 2 -> 3: `recent_tables`, most
  recent first, capped at `RECENT_TABLES_LIMIT` (10), each item
  `{"path", "at"}` with the persisted UTC timestamp
  `YYYY-MM-DDTHH:MM:SSZ` (strict format, length-bound); schema-2
  and schema-1 documents promote on load with `recent_tables=()`,
  and a schema-2 document carrying the field is refused as an
  unknown field (foreign schema, never silently promoted).
  `MasterApp.remember_recent_table` (prepend / dedup / cap /
  re-persist) is called at all three successful load points (the
  explicit `_start_load` path, the process-picker choice origin,
  the table-picker choice). The meta line shows `recent: a, b, c
  (N more)` (first 3); the status frame gains the "Recent:
  <path>" one-click load button (MT-10 path, width 28); the tree
  gains the indexed Size (compact B/KB/MB), Modified (local
  `YYYY-MM-DD HH:MM`) and Last-used (the stored UTC timestamp)
  columns; the window grows to 1160x600 / minsize 900x420. +13
  tests (`tests/test_native_master_recent.py`) + 5 UI tests in
  `tests/test_native_master_ui_mt13.py`.
- **Live-target takeover field fix** (code on `main` at `3ffa8fa`;
  documented here as 0.26 content): when a stale `state.lock` (or
  stale fence / artifacts) blocks the startup and the owner
  session is proven dead in both observations while ONLY
  target-side identities (session target, shared-lock target,
  journal targets) remain unproven and no other assessment reasons
  exist, all three startup probes yield the user-confirmed live-
  target takeover handle instead of the actionable refusal: the
  recovery archives the stale state byte-for-byte, releases the
  lock, and the new session attaches to the still-running game;
  saved wishes are re-applied (code-patch entries adopt via the
  idempotent current==actual path; AOB entries whose scan pattern
  no longer matches because the game already carries the previous
  session's patch surface as named scan errors with the bounded
  0.22 re-arm). Unprovable or live owners, foreign artifacts or
  any extra reason keep the strict refusal. `recovery.py`
  (`is_target_role` + `RecoveryAssessment.live_target_eligible`
  computed in `assess_recovery`), `recovery_operation.py`
  (`allow_live_target` gate on entry / fresh-reassessment / final
  probe - trainer-side identities must stay proven dead),
  `engine.py` (both handles carry `live_target_takeover`),
  `ui.py` / `master_ui.py` (dedicated "Recover and attach to the
  running game?" prompt). +19 tests (18 new in
  `tests/test_native_live_target_takeover.py` + 1 new foreign-
  artifact actionable-refusal test; 3 behavior tests updated).
- Regression fixes from the 0.26 change: `_meta_text()` had lost
  its `state: <home>` line (re-inserted after the `filtered:`
  block, before the MT-7 attach-gate block);
  `test_empty_state_roundtrip` now expects the schema-3
  `recent_tables: []` payload;
  `test_run_master_reuses_stored_folder_without_picker` persists
  through the current-schema state (by design,
  `master_state_to_bytes` refuses non-current schemas);
  `test_rescan_rerenders_after_content_change` asserts the 7-value
  row (Size / Modified / Last-used). Full main suite 4,320 OK /
  30 expected skips (2026-11-03); catalog remeasure
  `blocked-catalog-026-master-ui` (chunked 64x3 audit over the 151
  reference tables, 2026-11-03): 151/151 loaded, 0 load errors,
  117,809 total / 116,756 supported / 60,161 staged / 103,607
  actionable / 12,974 headings / 1,053 blocked - **zero delta** vs
  `blocked-catalog-026-live-target` (per-table count/reason/sha
  changes: 0); feature matrix unchanged (42/42, 7,475/7,475 over
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

### 0.23 Master Trainer roadmap complete + 0.23 release (2026-11-01, branch `native-0.23-master-roadmap` @ `b2d0344` + load-gate branch `native-0.23-load-gate` @ `98a9226`, main @ `6e3ec98`, build `native-20261101T145310Z-a160bae4`)

The remaining roadmap items MT-6/MT-7/MT-8 landed (two lane
subagents: `lane-mt8-frozen-entry` merge `deed3c5`,
`lane-mt67-sidecar-deck` merge `cee58b7`; root integration
`b2d0344`) together with the waiting-view observability work and the
ask-on-first-start table-folder parameter. No new trainer
functionality: the Master stays a wrapper around the tested engine.

- **MT-8 (frozen Master entry point, `tools/native_master.py` +
  `tools/native_build.py` build() area + `tests/test_native_master_frozen.py`
  +8):** the frozen `CT2Trainer-Master.exe` (PyInstaller onefile,
  `--windowed`, icon `src/ct2trainer/assets/Master_Trainer.ico`);
  argparse CLI mirroring the `master` subcommand exactly (optional
  positional `folder`, `--state-dir`, `--debug-log`, `--poll-ms`,
  `prog="CT2Trainer-Master"`); lazy `master_ui` import inside
  `main()` after argument parsing so `--help` (SystemExit 0) and the
  named exit-2 refusals (`folder not found` incl. file-as-folder,
  `--poll-ms must be a positive integer`) never touch tkinter or
  create any window (pinned by a `sys.modules` assertion).
  `build()` freezes the master after the converter through the same
  `freeze()` machinery (EXCLUDED set, hidden imports, NASM
  embedding) with **no `CT2BASE1` marker** (that marker is exclusive
  to the converter's template stub; the master consumes no
  templates); `inventory(master)` runs the CE-content scan, the
  master is the third entry of `payload-inventory.json` (template,
  converter, master), joins the `build.json` outputs and the
  portable ZIP next to `CT2Trainer-Converter.exe`, and gets a
  short "Also in this ZIP" README paragraph. `source_files()`
  admits `tools/native_master.py` via the existing `native_*.py`
  glob (pinned by test); `scripts/Build-Native.ps1` needs no change
  - its single `build --output` call emits the new EXE and ZIP
  entry. **The Master Trainer is now part of every build.**
- **MT-6 (per-table settings sidecar,
  `src/ct2trainer/native/master_trainer/settings_sidecar.py` +
  `tests/test_native_master_settings_sidecar.py` +17):**
  `MasterSettingsStore` keyed by the table **content sha256**
  (never by path - table identity survives folder moves; MT-5
  discipline: sidecars under the state home only), layout
  `<state home>/settings/<table_sha256>.ct2trainer.json` (the name
  ends with `.ct2trainer.json` so the existing `SettingsModel.save`
  contract accepts it unchanged; the path is built only from the
  validated 64-char lowercase hex sha + fixed relative layout, so
  path traversal is impossible - pinned by test). `load_for(table_sha256,
  known_record_ids, *, switch_ids=None, process_name=None)` is
  total: success `(document, [])`, absent file `(None, [])`
  (normal), `SettingsRejection` `(None, reasons)` displayable
  verbatim (caller shows, never silently defaults - the
  `settings_model` contract), structural `SettingsError`
  `(None, [named reason])`. `save_for(document, table_sha256)`
  derives `known_record_ids` as the union of the document's own id
  sets and refuses an all-empty draft with the named
  `nothing to persist` (no default file written); store-boundary
  refusals raise named `MasterSettingsRefusal`. On-disk bytes equal
  `document_to_json(document)` exactly (byte-stable, pinned by
  test). The tested `SettingsModel` is reused unchanged. UI wiring
  (root): `MasterApp.settings_store` property; restore on load in
  `_enter_trainer` (plan record ids as the known-id set,
  `process_name` from the plan; a refused stored document is shown
  via a named warning and the session continues without it), save on
  close in `_persist_sidecar` from both `_back_to_master` and
  `close()` (best effort; the named "nothing to persist" refusal
  never breaks the session lifecycle). The on/off wish persistence
  itself stays on the engine state store (MT-4, unchanged).
- **MT-7 (SteamOS / CheatDeck target route,
  `src/ct2trainer/native/master_trainer/steamdeck_route.py` +
  `tests/test_native_master_deck_route.py` +13):** the
  *documented-route surface* only - deliberately NOT a Linux attach
  backend. `AttachRoute` frozen dataclass
  (`platform` / `attach_available` / `route_name` / `detail`);
  `detect_platform()` (sys.platform: `win32` -> windows, `linux*` ->
  linux, else other); `attach_gate(platform=None)` - windows ->
  available through the unchanged `native-windows-engine` path,
  linux/other -> unavailable, `steamdeck-proton-wrapped` with the
  single shared `STEAMDECK_ROUTE_TEXT` (Proton-wrapped standalone
  CT2Trainer Windows trainer EXE, CheatDeck-compatible; the
  Linux/SteamOS Master runs detection + table index + waiting UI
  only; the owned Linux attach backend remains a later work item;
  fail-closed, no silent fallback); `require_engine_attach` raises
  the named `DeckAttachUnavailableError(ValueError)` carrying that
  text; `route_text` gives the displayable status-line hint. Pure
  stdlib, imports cleanly on Linux, platform parameterized so the
  linux/other paths are testable without mocking; a source
  inspection test pins the absence of any Windows-only API surface.
  UI wiring (root): the gate runs at the top of `_enter_trainer`
  before any engine work (a refusal shows the named error, fails
  the load through the orchestrator's `fail_load` path so the loop
  guard remembers it); the waiting view shows the route hint
  permanently in the metadata line on non-Windows. The real Deck
  protocol run with exact build hashes
  (`tests/deck/compatibility-matrix.md`) stays root/user field
  work.
- **Waiting-view observability (root, `orchestrator.py` +
  `master_ui.py`):** `TickOutcome.running` carries the live
  bound-process list (stable name/PID order) from every tick path
  (no-match, choosing-stable, deferred, all-unreadable, auto-load
  request, snapshot failure default); the waiting view gains a
  compact metadata line (table counts, bound process names, last
  scan time, the state home location) and a live "Running now" line
  (`Game.exe (PID 7)` per bound name, "(none of the bound
  processes)" when idle); table rows for a running process are
  marked `running` with their PIDs; the tree re-renders only when
  the visible (name, PID) set changes. +6 orchestrator tests
  (TickRunningFeedbackTests), +5 UI tests.
- **Ask on first start for the table folder** (CT source directory
  parameter; root, new `master_state.py` + `master_ui.py`
  `run_master` + `tests/test_native_master_state.py` +15 + 3 UI
  tests): the last-used table folder persists as
  `master-settings.json` in the state home (schema 1, canonical
  JSON payload with sha256 checksum envelope, 1 MiB size bound,
  foreign-schema/unknown-field/tampered-checksum/out-of-bounds
  refusals named `MasterStateRefusal`; tolerant load returns None
  for absent or refused documents - a fresh first start, never a
  silent reset). Folder resolution: an explicit `folder` argument
  (CLI `master` subcommand or frozen EXE) always wins and becomes
  the new persisted folder; without one, the stored folder is
  reused when it still exists; only a genuinely first start (or a
  stale stored folder) shows the directory picker. `MasterApp`
  gains `state_path()` / `persist_folder()` (persisted on start,
  on rescan-triggered folder changes via `set_folder`).
- **Package docs:** `ROADMAP.md` MT-6/7/8 rows done with exit
  evidence + recorded open design decisions (ask-on-first-start,
  MT-7 scope); `CONCEPT.md` status / waiting-mode / CLI / sidecar /
  platform-strategy / icon sections updated; `__init__.py` exports
  the new `master_state` / `settings_sidecar` / `steamdeck_route`
  surface.

- **MT-9 (load-time table compatibility & size gate, branch
  `native-0.23-load-gate`, merge `98a9226`):** `table_gate.py`
  `gate_table_for_load` re-proves one table file against its index
  entry at the moment the load is requested (auto-load or picker):
  missing file / not a regular file / stat-or-read failure / empty /
  over the 32 MiB load limit (33,554,432 bytes - the bound the table
  parser and the plan compiler enforce) / changed since the last
  scan (named stale refusal: Rescan refreshes the index and re-arms;
  also keeps the MT-6 sidecar keying - the table content sha256 -
  consistent with what the trainer loads) / not loadable by the
  tested `read_table` parser (malformed XML, DTD/entity input,
  unparseable legacy binary - the `LegacyCTError` named error passes
  through displayable) / changed during analysis. Cheapest-first
  ordering (no parser call for a stat-level refusal); every refusal
  a stable named code + displayable detail. The default plan
  compiler (master_ui.py) raises the named `TableLoadGateRefusal`,
  so a table load failure is graceful even when the target process
  was found: no crash, named error dialog + status line, the
  orchestrator's fail-closed loop guard records the exact (name,
  PID) pair (no hot-retry), Rescan / Retry load re-arm, and the
  orchestrator tick no longer re-issues the picker for a failed pair
  (named suppression until an explicit retry). `__init__.py` exports
  the gate surface; ROADMAP.md MT-9 row + CONCEPT.md waiting-mode
  gate bullet. Tests: new `tests/test_native_master_table_gate.py`
  +16 (pass with exact size+sha, sub-folder, ok-result shape, every
  named refusal code, no-parser-call proofs, change-during-analysis,
  refusal exception contract, stable codes),
  `tests/test_native_master_orchestrator.py` +2 (gate refusal via
  auto-load and via picker through the same loop guard, suppression
  + retry re-arm), `tests/test_native_master_ui.py` +4 (default
  compiler refuses drifted + missing tables with named codes,
  unchanged table passes through to `compile_table`, full
  `_start_load` refusal visible in dialog + waiting status line +
  guard armed + Rescan re-arms the request). Focused master suite
  235 OK / 4 expected skips; full main suite 4,155 OK / 30 expected
  skips at `98a9226` (canonical path, 2026-11-01).
- **Same-day field fixes merged after the MT-9 merge:** placeholder
  headings no longer create plan-level symbol dependencies
  (`28c9b57`, +10 tests in
  `tests/test_native_placeholder_heading_symbols.py` - the
  validate-plan symbol walk and the engine dependency walk now skip
  supported heading records (WP-32/WP-33 non-actionable
  placeholders); engine toggle of a placeholder heading performs the
  WP-53 own-state flip without a "Missing symbol provider" failure;
  control test proves the walk still refuses a selected supported
  record with an unresolvable symbol) and the Sinking City 2
  hotkey-bridge field fix from the 0.22.1 lane (branch
  `native-0.22.1-hotkey-bridge`, merge `4e9b95b`, +11 tests in
  `tests/test_native_sc2_hotkey_bridge.py`: T1 named missing-export
  guard - RegisterHotKeyW/UnregisterHotKeyW absence raises
  HotkeyRegistrationError instead of a raw AttributeError; T2
  engine containment - bridge faults become deduped per-entry
  hotkey warnings + one hotkey-bridge-failed debug event per
  distinct message, no engine block / poll-crashed / toggle
  downgrade / close refusal; T3 close protocol - message-only
  window on the loop thread, checked PostMessageW quit, same-thread
  DestroyWindow, class unregistered, deterministic close, no
  teardown AV; T7 persistence ordering - state-save precedes
  toggle-ok, failed enables persist nothing).

**Suite / catalog:** focused master suite 235 OK / 4 expected
skips; full main suite **4,176 run, OK (skipped=30)** on
`6e3ec98` (4,133 roadmap content + 22 MT-9 + 10 placeholder-heading
+ 11 SC2 hotkey-bridge; the 3 path-dependent
baseline-reproducibility tests fail in any non-canonical worktree
and pass at the canonical path - verified at the canonical path).
Catalog remeasures `blocked-catalog-023-master-roadmap` (on main @
`b2d0344`), `blocked-catalog-023-load-gate` (on main @ `98a9226`)
and `blocked-catalog-023-field-fixes` (on main @ `4e9b95b`, all
2026-11-01): each 151/151 loaded, 0 compile errors, 117,809 total /
116,756 supported (60,161 staged) / 1,053 blocked - **zero delta**
vs `blocked-catalog-022-rearm` (per-table count and reason changes:
0; no plan-builder code touched by this cycle).

**Build (2026-11-01, canonical path, `scripts/Build-Native.ps1`):**
run `native-20261101T145310Z-a160bae4` cut from `main` @
`6e3ec98`: in-build suite 4,176 OK / 30 expected skips
(`source_inputs_unchanged: true`), `ce_inputs: []`,
`runtime_unverified` deliberately kept per gate; source ZIP
`CT2Trainer-0.23-source.zip` sha256
`3360cab031cb1334dda71bb02a511170a9a70d1f583b5a8721624f46e24da464`
(14,291,040 bytes - carries the `master_trainer` subpackage incl.
`table_gate.py`, the MT-9 test file, the placeholder-heading + SC2
hotkey-bridge field-fix test files and the final 0.23 changelog
entry), portable ZIP
`CT2Trainer-0.23-windows-portable.zip` sha256
`eec023ba09e8fcb80608736896f0477f4a783034046e6ad67514e96ed0a2905b`
(49,609,916 bytes - the frozen `CT2Trainer-Master.exe` (sha256
`e5822f688c653242a9f64bd92e4ba92529d485b89c11607cf20d32e728ca3c20`,
16,895,048 bytes) ships next to the converter); all three on-disk
EXEs (Template / Converter / Master) byte-identical to the
`build.json` outputs; the payload inventory carries the master
entry with the `Master_Trainer` icon assets. First recorded build
to emit `CT2Trainer-Master.exe` into the run folder and the
portable ZIP. (Two earlier same-day cuts were deleted before
recording: `native-20261101T101907Z-fc808a12` - cut before the
MT-9 merge, run folder misplaced by the launcher cwd resolution -
and `native-20261101T134313Z-b637e493` - invalidated by the
fail-closed source-change check because the changelog finalization
landed mid-build; its in-build suite had run 4,155/30 at the
time.)

### 0.22 field cycle: FO4 re-arm + SC2 hotkey-bridge findings (2026-11-01)

**Field inputs (local-only evidence, never committed):**

- **Fallout 4** (trainer 0.20, Steam Deck / Proton, 2026-10-31
  13:37-13:45 UTC, target pid 696): auto-attach OK; 8 auto-on wishes
  queued pre-attach; 6 of 8 wish restores `ScanMiss`ed while the game
  was still loading (43 OK; 1052 AOB first match OK then second
  ScanMiss; 7/12/30/976/1095/1096 ScanMiss); 15+ manual taps all
  ScanMiss; value-read failures on identifiers 943/944/924/931/927/
  937/126/880 (`Invalid, overflowing, or oversized memory range` -
  unresolved pointer chains, expected; 0.19 `value-read-failed`
  observability covers it); `target-exited` 13:45:27; restarts hit
  `StaleStateRecoverable` / `StaleArtifactsRecoverable` with the
  recovery prompt working.
- **The Sinking City 2** (trainer 0.19, 3 sessions): S1 Windows
  2026-10-30 21:19 (trainer PID 26412, target 13300); S2 Windows
  2026-10-31 12:31 (first restart PID 3684 refused by the state-lock
  process proof, second start PID 12600 recovered 12:31:47, target
  2776, all 6 wishes restored, attached 12:32:03); S3 Steam Deck /
  Proton 2026-10-31 15:25 (PID 416, target 336). Hotkey registration
  worked on the Deck (Wine has the export); the `RegisterHotKeyW`
  AttributeError is Windows-specific; the close-timeout + AV
  reproduces on both platforms.

**Re-arm package (0.22, this cycle):** branch
`native-0.21-fo4-rearm`, commit `5704fd2`, merged `main` @ `a12a0b6`
(5 files, +1,005/-62; lane report reviewed, clean-room taint-scan
clean - only two benign "Fallout 4 under Proton" field-case
annotations):

- Bounded automatic re-arm of `ScanMiss` enable failures:
  `REARM_INTERVAL_SECONDS = 30` / `REARM_MAX_ATTEMPTS = 10` module
  constants (`engine.py:60-61`). Arming points: manual toggle
  (`engine.py:5547`) and restore loop (`engine.py:2645`) with
  `fresh_attempt=False` (the first enable of a session consumes no
  budget); executor (`engine.py:2787`) and `try_again`
  (`engine.py:2898`) consume one attempt each. `_run_rearm`
  (`engine.py:2744`) runs in the attached poll after
  `_hotkey_sync()`: skips blocked/busy/unattached, pops arms whose
  entry became applied, skips exhausted/not-due, re-runs the full
  enable path (`_dependencies(persist=False)` +
  `_enable(persist=True)`). Success pops the arm, clears
  `enable_failures`/`entry_errors`, persists the confirmed wish,
  `rearm-succeeded`; ScanMiss consumes an attempt and pushes the
  cadence; other failures pop the arm and log
  `rearm-attempt(result=<exception class name>)`, with
  PatchConflict/StateError blocking the engine.
- Budget reset + `reattach-done {pid}` on every confirmed (re-)attach
  (`engine.py:2542-2559`): all armed entries
  `attempts=0, due=now, exhausted=False`; non-wish armed entries
  retry immediately on the next tick; wish entries are restored by
  the restore loop first, whose failure pushes `due=now+30` (no
  same-tick double attempt).
- `self.rearm` / `self.enable_failures` deliberately survive
  `_detach_current_target()` (`engine.py:2671`, extracted verbatim
  from the target-exited poll branch) - the fresh budget lands with
  the next confirmed attach, so a restarted game process re-arms
  everything.
- Toggle OFF while armed disarms silently; exhaustion stops automatic
  retries; only manual "Try again" resets the budget after
  exhaustion; value-read failures and all non-ScanMiss named
  refusals are never armed (plain-failed contract unchanged).
- Manual "Try again": `try_again` (`engine.py:2862`) refuses via
  `_guard` (not attached) or "already enabled"; resets the arm
  before the attempt; success pops the arm (`rearm-succeeded` only
  if armed); ScanMiss re-arms with a fresh attempt;
  `NativeRuntimeError` re-raised for the UI status line. UI:
  `RowSnapshot.enable_failed`/`.rearm` (validated in
  `__post_init__`, included in the render signature), pure
  `rearm_sublabel` / `try_again_available` helpers in `ui_rows.py`,
  "Try again" as a 3-tuple context-menu item with disabled state
  routed through `self.action(...)`; sublabel precedence: re-arming
  > enable failed.
- Top-level "Re-attach" header button after "Status / help"
  (`ui.py:196`, `on_reattach`): `reattach` (`engine.py:2923`) refuses
  named while closed/blocked/busy; attached -> `reattach-detached` +
  detach; unattached -> waits, and the normal attach cycle proceeds.
  `_log_reattach_failure` (`engine.py:2730`) dedupes
  `reattach-failed {reason}` per request across the five unattached
  attach-failure points (`engine.py:2479/2486/2495/2503/2518`).
- JSONL events: `rearm-scheduled`, `rearm-attempt {identifier,
  attempt, max, result}`, `rearm-succeeded`, `rearm-exhausted
  {attempts}`; `reattach-requested`, `reattach-done {pid}`,
  `reattach-failed {reason}`, `reattach-detached`. No tracebacks on
  repeats.
- `tests/test_native_rearm.py` (+17: 10 engine scenarios, 7 UI/pure
  incl. RowSnapshot validation, sublabel/try_again_available pins,
  context-menu 3-tuple, header button). Lane evidence: focused 17
  OK; regression batches 246 + 172 OK across 21 modules.

**Suite / catalog:** full canonical suite on `main` @ `a12a0b6`
(2026-11-01): **4,061 run, OK (skipped=30)** (4,044 from the 0.21
build + 17 re-arm; the 3 path-dependent baseline-reproducibility
tests pass at the canonical path). Catalog remeasure
`blocked-catalog-022-rearm` (2026-11-01): 151/151 loaded, 0 compile
errors, 117,809 total / 116,756 supported (60,161 staged) / 1,053
blocked - **zero delta** vs `blocked-catalog-020-rt5-be`.

**Build (2026-11-01, canonical path, `scripts/Build-Native.ps1`):** run
`native-20261101T075049Z-f32c112d` from `main` @ `2b24a1c` - in-build
suite **4,061 OK / 30 expected skips, 0 failures** (fully green,
incl. the 3 path-dependent baseline-reproducibility tests),
`ce_inputs: []`, `runtime_unverified` deliberately kept per gate;
`CT2Trainer-0.22-source.zip` sha256
`c5db1b92c8851d4937e2544a77bd0787c5d48c941ebcfef8741cf4ae104ac7cf`
(14,243,974 bytes) - carries the re-arm tests
(`tests/test_native_rearm.py`) and the 0.22 changelog entry - and
`CT2Trainer-0.22-windows-portable.zip` sha256
`f89cd0225b5d439bf18106728c3a89e906e56957fd28b9b7b2b5e16f5c3c221a`
(33,023,506 bytes).

**SC2 hotkey-bridge findings (P0, next field-fix cycle - NOT fixed in
0.22; hotkey-bridge code unchanged):**

1. **T1 - unguarded missing-export path.** `hotkey_bridge.py:343-351`
   sets the `_hotkey_api_available = False` guard when
   `RegisterHotKeyW` is absent from user32, but `register_hotkey`
   (:403-405) and `unregister_hotkey` (:407-409) call
   `user32.RegisterHotKeyW(...)` / `user32.UnregisterHotKeyW(...)`
   unconditionally -> raw `AttributeError` where the module
   docstring promises a named, non-blocking
   `HotkeyRegistrationError` (S1 21:19:43.657 `toggle-failed` on
   entry 198/F2; S2 12:32:06.433 `poll-crashed`).
2. **T2 - hotkey failure hard-blocks the engine.** The
   AttributeError escapes `_hotkey_sync` through toggle and poll;
   S1 entry 198 shows `toggle-ok` **and** `toggle-failed` (the
   programmatic enable had succeeded); S2's `poll-crashed` ->
   `engine-blocked` then refuses every toggle (13:15:17-26, five
   refusals) and `close()` (15:11:21, `engine.py:5974`). Product
   rule: a hotkey-registry failure is a named per-entry warning
   (`engine.hotkey_warnings`), not an engine fault.
3. **T3 - deterministic close-timeout + AV (3x: Windows x2 + Deck
   x1).** Root cause in code: `connect()` creates the message-only
   window on the main thread (`hotkey_bridge.py:381`); the loop
   thread (:390-396) pumps `GetMessageW` with `hwnd=None` - its own
   queue, which never receives the window messages; `WM_BRIDGE_QUIT`
   posted to the window (:415) is only deliverable when the creating
   thread pumps - i.e. the main thread - but `destroy()` (:414-423)
   blocks the main thread in `loop_thread.join(timeout=5.0)` while
   waiting for a flag only the loop thread sets -> guaranteed 5 s
   timeout ("hotkey bridge message loop did not stop within 5s") ->
   `DestroyWindow` never reached -> the daemon loop thread AVs in
   `GetMessageW` during process teardown (faulthandler dumps;
   `PostMessageW` return unchecked). Fix options: (a) create the
   window on the loop thread so the quit protocol works as designed,
   or (b) drop the loop thread - the window lives on the main thread,
   `destroy()` calls `DestroyWindow` on its own thread, hotkey
   dispatch already rides the Tk event loop. Both keep the WP-53
   contract (WM_HOTKEY -> queue -> `_hotkey_sync` drain).
4. **T4 - transient-read PatchConflict (Win32 299).** S1 22:19:19
   (~1 h after attach): `_check_patches` -> `hooks.check_entries` ->
   `ReadProcessMemory failed (Win32 error 299)` -> `PatchConflict`
   `engine-blocked`. A transient read failure (target mid-decommit /
   AV / exit) must surface as a named retryable state, not a receipt
   change; verify the periodic check cadence and which read calls
   are involved.
5. **T5 - state-lock first-restart refusal.** S2 12:31:27 (PID
   3684): `StateError` - "Recovery hashes, file identities, or
   directory inventory changed during process proof; Exact process
   13300/... is not proven dead in both observations (absent); Exact
   process 26412/... (absent)". Both processes were absent, yet the
   proof failed; the second start (PID 12600, 12:31:45) got
   `StaleStateRecoverable` and recovered cleanly. Open: why the
   first observation set is not "proven dead", what changed in the
   inventory during the proof (self-inflicted by the startup
   attempt?), and whether "absent" should count as dead.
6. **T7 - wish persisted before toggle-failed.** S1 entry 198: the
   `state-save` persisting wish [198] precedes the `toggle-failed`
   event. Violates "only confirmed ON-switches are persisted";
   linked to the T2 fix (a hotkey failure must not follow a
   successful programmatic enable).
7. **T8 - value-read errors during game load (documented).** FO4: 8
   identifiers while the engine was still loading; expected with
   unresolved pointer chains; covered by 0.19's
   `value-read-failed` observability; no code change.
8. **T9 - no WM_HOTKEY dispatch observed.** Neither log contains a
   successful hotkey dispatch (F2 not pressed in the observed
   windows; S1/S2 registrations failed on Windows). Next field
   test: press a bound hotkey and expect the `hotkey-*` events.

**Open work after this cycle:** SC2 hotkey-bridge fix lane
(T1-T3, then T4/T5/T7) pending user go-ahead; user field test of the
0.22 re-arm (FO4: wish restore during load); then RT-6
(verification) and RT-7 (final acceptance) per
`plans/reference-table-100-roadmap.md`; closing docs (a) CE 7.5 vs
CT2Trainer comparison refresh and (b) next-work roadmap; cleanup of
merged lane branches/worktrees (`native-0.21-fo4-rearm` +
`lane-fo4-rearm`, plus the older `lane-rt5-b`, `lane-ce-analysis`,
`jolly-canyon`, `curious-pixel`).

## 3. Deterministic measurement chain

All committed `gap_inventory/` artifacts are reproducible byte-identically
from the committed corpus with a fixed run id. Stage 2 and stage 3 refuse
to write into the directory that contains their input artifacts, so each
writes to a scratch directory and the result is copied into
`gap_inventory/`; stage 3 consumes the committed
`gap_inventory/feature-coverage.json` so its provenance matches the
committed manifest:

```
python tools/corpus_denominator/__main__.py --corpus TableReferences --output gap_inventory --run-id repo-reproducible
python tools/corpus_denominator/feature_matrix.py --gap-report gap_inventory/gap-report.json --inventory gap_inventory/inventory.json --output <scratch2> --run-id repo-reproducible
copy <scratch2>/feature-coverage.json gap_inventory/feature-coverage.json
python tools/corpus_denominator/ap11_campaign.py manifest --gap-report gap_inventory/gap-report.json --inventory gap_inventory/inventory.json --feature-coverage gap_inventory/feature-coverage.json --corpus-root TableReferences --output <scratch3> --run-id repo-reproducible
copy <scratch3>/ap11-campaign.json gap_inventory/ap11-campaign.json
```

The committed artifacts are the reference; gate:3
(`tests/test_native_repro_chain.py`) re-runs the full chain and compares.
Corpus: 30 synthetic case tables (`TableReferences/case-01.ct` …
`case-14.ct`, `case-15.ct`, `case-16.ct`, `case-17.ct`, `case-18.ct`,
`case-19.ct`, `case-20.ct`, `case-21.ct`, `case-22.ct`, `case-23.ct`,
`case-24.ct`, `case-26.ct`, `case-27.ct`, `case-28.ct`, `case-29.ct`,
`case-30.ct`, `case-31.ct`; case-to-origin mapping in
`TableReferences/README.md`), 143 distinct SHA-256 hashes collapsed
to 30 pinned cases, 6143 expected actions (run
`w4b4-case30-20261020081722Z`).

## 4. Prioritized open work

The active outcome is [100% original reference-table support](../plans/reference-table-100-roadmap.md).
The old 85% closure estimate and 0.11 release step were superseded by the
0.16 Wave-4 release and the new target. Priorities are:

1. **RT-4 and RT-5 (RT-1/RT-2 done 2026-10-21, RT-3 done 2026-10-23,
   RT-4.1 done 2026-10-22, RT-4.4 done 2026-10-23, RT-4.5 done
   2026-10-24, RT-4.6 done 2026-10-24, RT-4.3 done 2026-10-26,
   RT-4.2 done 2026-10-27, RT-5 inventory done 2026-10-23):**
   the 151-path/143-hash manifest is frozen; every remaining blocker is
   attributed to an upstream cause with per-class contracts, risks and
   expected deltas (RT-2 root-cause map in the roadmap). RT-4.1 symbol
   provider fidelity landed (keep-first duplicate-provider policy,
   `label()` duplicate-name tolerance, wildcard-cleanup scoping; catalog
   remeasure 2,698 -> 1,858 blocked, net -840, 2 explained Cyberpunk
   shared-global regressions, zero unexplained supported regressions —
   see the RT-4.1 section above). RT-3 legacy-binary CT loading landed
   (clean-room parser + documented conversion path; table load 151/151,
   `SuperMeatBoy.CT` 10/10 supported — see the RT-3 section below).
   RT-4.4 value semantics landed (dropdown width truncation + expression
   choices per the CE SetValue conclusions, ShowAsHex byte-array
   profiles, empty read-only dropdown display views, O11 custom-type
   gate kept by design — see the RT-4.4 section below). RT-4.6 input
   legacy & authoring gaps landed (actionable per-symbol 'not registered
   anywhere' report with raw-source registration survey, x87 st/st(N)
   FPU-operand fold, user-symbol import — see the RT-4.6 section above).
   RT-4.5 AA directive & script coverage landed (aobscanregion + CE
   dealloc name-list semantics, usemono parity-scope refusal,
   three-segment managed labels, global DISABLE reset regions,
   symbol-only luaCall envelopes, label/data global-region closure —
   see the RT-4.5 section above). RT-4.3 address expression &
   identifier dialect landed (O1 relative-address skip-fold + O9
   runtime-base marker staging, O3 pointer-offset expression slots,
   O10 identifier dialect, O23 token-named quoted-atom refusal,
   O27/O4 Type:Member managed labels, O13 directive-aware string data
   bytes — see the RT-4.3 section above; catalog remeasure
   `blocked-catalog-rt43-main` 1,743 -> 1,351 blocked, net -392, zero
   newly blocked). RT-5 item G createThread/threadWait gate decision
   landed (lane `native-rt5-g`, merge `2de9c0e`): option (2) recorded —
   capability gate stays, no thread backend ships this milestone;
   byte-stable five-stage gate pins
   `tests/test_native_rt5_thread_gate.py` +17 (focused 17 OK; main
   suite 3,648 OK / 25 expected skips); census re-derived: exactly 2
   O22 rows (Witcher3 4.02HF1_G25v2 + 4.03_G25v2, id 192) and 77
   first-word `createThread` usages across 18 tables split into 26 AA
   directive lines in 8 tables (gate-governed) and 51 Lua-context lines
   in 11 tables (`lua_host` cooperative workers, separate family);
   tests only, zero catalog movement (`blocked-catalog-rt5g-main` zero
   delta). RT-5 item F no-effect register ratification landed
   (lane `native-rt5-f`, merge `966fccd`): the inventory §8
   no-effect/out-of-scope register is pinned as an enforced byte-stable
   contract — `tests/test_native_rt5_no_effect_register.py` +22 (focused
   22 OK; main suite 3,670 OK / 25 expected skips); tests-only, zero
   catalog movement (`blocked-catalog-rt5f-main` zero delta). RT-4.2
   runtime provider model landed (lane `native-rt4-2`, merge
   `bb86983`): keep-first duplicate-provider scope fallback (R3),
   mixed-dialect `unregistersymbol` release evidence per the CE 7.5
   AA/Lua contracts (R4), bounded API-export registry with
   link-time resolution (R7) — see the RT-4.2 section above; catalog
   remeasure `blocked-catalog-rt42-main` 1,351 -> 1,053
   blocked, net -298, zero newly blocked. RT-4 is complete;
   next: the RT-5 implementation items A-E. The user-requested trainer
   UI feature (Scripts view + row context menu with script preview and
   entry assessment) landed 2026-10-24 on branch
   `native-0.17-ui-script-inspector` (suite 3,587 OK / 25 expected
   skips; catalog remeasure `blocked-catalog-ui-scripts` zero delta —
   see the Trainer UI section above); it ships in the 0.17 build cut
   after the remaining RT-4.x merges (user decision 2026-10-24). The
   latest snapshot has **1,053/117,634 blocked entries**, 116,581
   supported (60,161 staged), and zero load errors (run
   `blocked-catalog-rt42-main`). This is static evidence only.
2. **RT-5 implementation items A-E:** RT-4.x is complete (RT-4.2
   runtime provider model landed 2026-10-27, merge `bb86983`); RT-5
   items F (no-effect register ratification) and G (createThread/
   threadWait gate decision) landed 2026-10-26, tests-only. Remaining:
   the RT-5 implementation items A-E inventoried in
   `documentation/rt5-api-inventory.md` (embedded-file loader contract,
   bounded process-info APIs, table-callback dispatch, CheatCodes
   code patches, messageDialog decision) with independent synthetic
   cases and owned-target tests.
   Pure visual Forms rendering (WP-42) is outside the requested
   trainer-behavior scope; any form control that causes a game-facing
   action remains in scope.
3. **RT-6 and AP-11:** verify original-table behavior against pinned game
   builds and run the 6,143-action synthetic campaign. The campaign has
   **0 confirmed effects**; its runbook is
   [`native-ap11-campaign.md`](native-ap11-campaign.md).
4. **Platform acceptance:** complete Windows clean-machine and real
   Steam Deck/Proton/touch protocols. Record build ID, ZIP hashes, setup,
   observations and failures before changing `runtime_unverified`.
5. **RT-7 release:** build offline with `scripts/Build-Native.ps1`, audit
   source/frozen parity and CE-free payload, then publish a release only
   after the documented gates pass.

## 5. Maintenance protocol

- Every integration: full suite green, matrix/artifact regeneration with
  one fresh run id where applicable, plan + ledger updated in the same
  change, push per the workflow policy in `AGENTS.md`.
- Gate flips happen only with real, tested evidence; gate action weights
  remain 0 (completeness/proof features, not record actions).
- No blind cleanup of `build/runs/`, `.tools/`, `dependencies/`,
  `gap_inventory/` or fixtures.
- Reports under `build/runs/` are historical for their pinned bytes only;
  if inputs changed, re-run the checks instead of re-reading old logs.
- Subagent lanes run under `documentation/subagent-lane-rules.md`;
  before launching lanes, check model-server load with
  `tools/agent_load.py`.
- Distributed releases never contain dev ledgers, plans, or corpus
  scratch: the build allowlist in `tools/native_build.py`
  (`source_files()` / `RELEASE_DOC_FILES`) is the single source of truth
  and is verified by the in-build CE-content scan.
