# CT2Trainer: Native progress ledger

**Central tracking:** all open gaps, goals, work packages, corpus cases and
the measurement snapshot are tracked in one place:
[`plans/TRACKING.md`](../plans/TRACKING.md). This ledger keeps the
confirmed-state detail (builds, suites, acceptance records); when in doubt
about current status, check the tracker first.

Status: **October 21, 2026** (0.16.1 released, build
`native-20261021T161241Z-b0566a25` cut from `main` @ `d1c61f2`; previous
0.16 field-fix re-cut 2 `native-20261021T123801Z-8c5c4e1e` @ `108170b`,
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

## 2. Confirmed state (0.9.0-rc2 + WP-14..58 + 0.16 field-fix re-cut 2, 2026-10-21)

| Item | Value |
| --- | --- |
| Repository baseline | `main` @ `b6c48cc` "initial 0.9 version" (self-contained clean-room tree) |
| Version | `0.16` (root `VERSION` file; 0.9.0-rc2 was the last user-tested release, 0.16 user-tested 2026-10-20 with the WP-58 startup crash, fix in the re-cut) |
| Test suite | **3412 OK / 25 expected skips, 0 failures** (full local dev suite on `main` after the 0.16.1 SC2 table-load warning fix — table-version reference 45 → 46 + accurate `{$LUA}`/external-action warnings (`tests/test_native_sc2_table_warnings.py`, version assertion in `tests/test_native_compiler.py`), verified 2026-10-21 at the canonical path with CT2TRAINER_NASM set; previously 3405 on `main` after the 0.16 field-fix round 2 — state-lock self-repair and reliable restart (`tests/test_native_stale_lock_selfheal.py`, updated variant-close assertion in `tests/test_native_engine.py`), verified 2026-10-21 at the canonical path with CT2TRAINER_NASM set; previously 3398 on `main` after the 0.16 field-fix cycle — WP-58 UI startup crash fix + Sinking City 2 runtime chain evidence (`tests/test_native_ui_button.py`, `tests/test_native_sc2_attach_chain.py`), verified 2026-10-20 at the canonical path with CT2TRAINER_NASM set; previously 3393 on `main` after the W4 B4 merges and the case-28/29/30 pins, verified 2026-10-20 at the canonical path; previously 3233 on `main` after the W4 cycle merge and the case-26/27/31 pins, verified 2026-10-19 at the canonical path; previously 3057 on `native-0.15` after the W3 batch 1 + batch 2 + batch 3 + batch 4 merges (WP-39/40/38/41/37) and the case-23 + case-21 + case-22 + case-24 pins, verified 2026-10-18; previously 3046 after the W3 batch 3 merge (WP-41) and the case-22 pin; previously 3001 after the W3 batch 1 + batch 2 merges (WP-39/40/38) and the case-23 + case-21 pins, verified 2026-10-18 at the canonical path; previously 2943 after the 0.15 prefix-cut field fix at `d15268a`, 2026-10-17; previously 2932 on `native-0.14` after the per-wish restore isolation and program-scan debug logging, verified 2026-10-17 at the canonical path; previously 2927 on `native-0.13` after the optional debug-logging feature incl. attach-failure dedupe and the module-snapshot fallback, verified 2026-10-16; previously 2925 after the debug-logging feature; previously 2910 after the W2-C + W2-B merges and the case-15 part 2 + case-18 pins; previously 2840 after the W2-A merge and the case-20 + case-16 + case-17 + case-15 pins, verified 2026-10-14; previously 2805 after the W1-A + W1-E merges and the case-20 + case-16 + case-15 pins; previously 2769 after the W1-D + W1-C + W1-B integration; previously 2710 after the WP-18 merge `9a76eb8`; previously 2698 after the WP-17 merge `557b2ac`; previously 2688 after the WP-15 merge `d3316aa`; previously 2679 on `native-l5-19` after the WP-16 merge `38a830d`; previously 2671 on `native-0.9-staged` after the WP-14 gate-test merge `54b172e`); in-build suite 2932/25 passed (0.14 build `native-20261017T115850Z-1ebb48b7`); previously 2927/25 (0.13 build `native-20261016T190005Z-b3139b30`); previously 2925/25 (superseded 0.13 build `native-20261016T181516Z-b8ae88de`); previously 2910/25 (0.12 build `native-20261016T163910Z-d047f2d2`); previously 2710/25 (0.11 build `native-20261012T092729Z-2d8aaf12`); previously 2698/25 (0.11 build `native-20261011T182033Z-f3317337`); previously 2671/25 (0.10 build `native-20261011T121914Z-bfc5fc11`) |
| Feature matrix | **42/42 covered** (100% feature-weighted, 7475/7475 action-weighted; run `w4b4-case30-20261020081722Z`; previously 7446/7446, run `w4-case31-20261019061339`; previously 7426/7426, run `w3e-case24-20261018051230`; previously 7416/7416, run `w3d-case22-20261018040510`; previously 7413/7413, run `w3b-case21-20261018023823Z`; previously 7411/7411, run `w3-case23-20261018012531Z`) — `gap_inventory/feature-coverage.json` |
| AP-11 manifest | 30 tables, 6143 expected actions, 0 confirmed, all consistency gates `all_ok` (run `w4b4-case30-20261020081722Z`; previously 27 tables / 6119 actions, previously 24 tables / 6100 actions, previously 23 tables / 6092 actions) — `gap_inventory/ap11-campaign.json` |
| Latest verified build | `native-20261021T161241Z-b0566a25` (0.16.1, first build under the new versioning rule) via `scripts/Build-Native.ps1` from `main` @ `d1c61f2` (2026-10-21): both ZIPs (`CT2Trainer-0.16.1-source.zip` sha256 `13e2e1f6…`, `CT2Trainer-0.16.1-windows-portable.zip` sha256 `5d8f0d47…`), in-build suite 3412 OK / 25 expected skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per gate; both ZIPs carry the changelog with the 0.16.1 entry (Sinking City 2 table-load warnings made accurate + versioning rule) + 0.16 + 0.15 + 0.14. 0.16.1 ships the SC2 table-load warning fixes (table-version reference 45 → 46 field-verified; `{$LUA}` warning states the built-in Lua runtime path; external-action warning split per API — ShellExecute safe no-op, messageDialog review flag) on top of the 0.16 content. 0.16 ships the full Wave 4 feature set (WP-43…WP-57 + WP-58 UI) plus the post-release field fixes (WP-58 UI startup crash fix + Sinking City 2 activation-chain runtime evidence + state-lock self-repair and reliable restart) on top of the released 0.15 content. Superseded 0.16 runs: `native-20261021T141051Z-17d53c1d` (0.16, cut from `main` @ `e9f06fb` after the RT-1 rebaseline, in-build 3405/25, `ce_inputs: []`, superseded by the 0.16.1 cut before its evidence was recorded), `native-20261021T123801Z-8c5c4e1e` (0.16 field-fix re-cut 2, cut from `main` @ `108170b`, in-build 3405/25, user-tested, field finding: Sinking City 2 table-load warnings), `native-20261020T150115Z-c426fb92` (cut from `main` @ `7616edb`, in-build 3398/25, user-tested, field findings: one cheat = table/build mismatch, state-lock orphan after a blocked close) and `native-20261020T103508Z-0e3f9d90` (cut from `main` @ `809666a`, in-build 3393/25, user-tested, shipped with the WP-58 UI startup crash). Previous: `native-20261018T055505Z-39f20180` (0.15) via `scripts/Build-Native.ps1` from `main` @ `ed0b97b` (2026-10-18): both ZIPs (`CT2Trainer-0.15-source.zip` sha256 `5d5a85f6…`, `CT2Trainer-0.15-windows-portable.zip` sha256 `cfcc8e06…`), in-build suite 3057 OK / 25 expected skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per gate; both ZIPs carry the elaborated release READMEs and the changelog with the 0.15 + 0.14 + 0.13 entries. 0.15 ships the prefix-cut byte-patch validation (the 0.14-ext2 Great Circle field finding: Stealth Mode and No Reload use `db 90 E9` over a 6-byte conditional jump, now proven at link time and re-verified at stage time) plus the full Wave 3 feature set on top of the 0.14 content. Previous: `native-20261017T115850Z-1ebb48b7` (0.14, in-build 2932/25); `native-20261016T190005Z-b3139b30` (0.13, in-build 2927/25); `native-20261016T181516Z-b8ae88de` (0.13 pre module-snapshot fallback, in-build 2925/25); `native-20261016T163910Z-d047f2d2` (0.12, in-build 2910/25); `native-20261016T161905Z-e8ef67a0` (0.12, byte-identical re-cut); `native-20261016T154141Z-2de774ab` (0.12 pre release-docs); `native-20261012T092729Z-2d8aaf12` (0.11, in-build 2710/25); `native-20261011T121914Z-bfc5fc11` (0.10, in-build 2671/25); `native-20261010T172336Z-ffe35eb0` (rc2, in-build 2617/25, `api-prototypes.json` present in both EXE payload inventories, user-tested portable) |
| User-tested portable | run `native-20261010T165731Z-3d1da645`: converter run + generated trainer verified by the user on a machine without CE/Python |
| Reference-corpus assessment (2026-10-13) | 151 local-only reference tables: baseline 117,019 plan entries, 95,167 supported (incl. 46,987 staged), **21,852 blocked**, 4 whole-table compile errors (run `ref-assessment`); after W1-D (WP-25) + W1-C (WP-22/23): **21,851 of 117,255 blocked**, 3 whole-table compile errors — Octopath compiles (227 supported / 9 blocked, 24 duplicate-ID warnings), 20XX fully supported (10/10), SuperMeatBoy refused with a named legacy-binary error (catalog re-run 2026-10-13); after W1-B + W1-A + W1-E: **10,892 of 117,624 blocked**, 1 whole-table compile error (SuperMeatBoy legacy binary only; AtomicHeart `$process` closed by WP-19, Cyberpunk `@@` by WP-20) (catalog re-run 2026-10-14); after W2-A (WP-27/32/33/34): **9,962 of 117,624 blocked**, 1 whole-table compile error (SuperMeatBoy only; catalog re-run 2026-10-14, `blocked-catalog-w2a.json`; −930 blocked, 0 supported regressions, +197 previously masked records now surface the named missing-target reason); after W2-B + W2-C (WP-28/29/31/35 + WP-30/36): **7,577 of 117,624 blocked** (−2,385, 0 supported regressions; 1 whole-table compile error, SuperMeatBoy only; catalog re-run 2026-10-16, `blocked-catalog-w2final.json`); after W4 B1–B3 (WP-43/44, WP-46 part 1, WP-47/55, WP-45/56, WP-51/48, WP-52): **3,632 of 117,624 blocked** (−3,945, supported 113,992 incl. 58,018 staged; 1 whole-table compile error, SuperMeatBoy only; catalog re-run 2026-10-19, `blocked-catalog-w4final.json`); after W4 B4 (WP-46 part 2, WP-49/50, WP-53/54, WP-57, WP-58): **2,698 of 117,624 blocked** (−934, supported 114,926 incl. 58,950 staged; 1 whole-table compile error, SuperMeatBoy only; catalog re-run 2026-10-20, `blocked-catalog-w4b4.json`); consolidated assessment `documentation/reference-gap-assessment.md`, closure plan `plans/archive/reference-closure-continuation.md` (WP-19…WP-42) |

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
lane's `rt2_final2` run.

**Decomposition:** 2,698 = 1,931 provider-cascade rows + 767 direct
rows. Cascade terminals: 1,304 undefined-symbol rows - 963 AA_HIDDEN
(in-table registration the analyzer misses), 110 LUA_RUNTIME (table Lua
`registerSymbol` providers), 91 NO_REG (no static registration evidence;
runtime host/user-provided or authoring gap, per-symbol triage), 128
LEGACY_SYM (CE built-ins/keywords such as BaseAddress, Inf, assembly
mnemonics, table-local bases), 12 API_EXPORT (Win32 exports) - plus 624
duplicate-provider cascades (600 = five shared UE5 template tables x 120
`character_pointer`) and 3 wildcard-cleanup conflicts. The 2026-10-20
queue's leading reason occurrences decompose exactly: `Esau_base` (600)
-> duplicate-provider cascades; `mouse_ovr` (84) + `loot_ptr` (62) ->
AA_HIDDEN in the Witcher3 pair; `BaseAddress` (80) -> LEGACY_SYM across
the five UE5 template tables; pointer offsets (53) -> direct
hex-literal refusals.

**Per-class testable contract, risk and expected delta** are recorded in
the [RT-2 root-cause map](../plans/reference-table-100-roadmap.md)
(section "RT-2 root-cause map"), with the RT-4 package split summing
exactly to 2,698: P1 duplicate-provider/duplicate-label policy 814,
P2 hidden in-table registration cascades 963, P3 Lua runtime symbol
providers + no-registration triage + Lua-only enables 203, P4 relative-address base
propagation 341, P5 legacy built-ins + API exports 140, P6 AA
expression/directive grammar & format tolerance 122, P7 AA
ownership/cleanup envelope & table-level constructs 43, P8 value/display
semantics 64, documented authoring/scope refusals 8. Headline parity
findings: dropdown overflow - CE 7.5 truncates (verified at
`MemoryRecordUnit.pas:3500`), CT2Trainer refuses (30 rows, P3R family);
module references without `.exe` do not resolve in CE either (module
list stores names with the extension, `symbolhandler.pas:5753`); IL2CPP
`Type:Member` has no native static resolution in CE (pipe-server
commands only, `PipeServer.h:194-367`) and belongs to the RT-5 runtime
path.

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

1. **RT-3 and RT-4 (RT-1/RT-2 done 2026-10-21):** the 151-path/143-hash
   manifest is frozen and the 0.16 catalog reproduced; every remaining
   blocker is attributed to an upstream cause with per-class contracts,
   risks and expected deltas (RT-2 root-cause map in the roadmap). Next:
   the legacy-binary table (RT-3) and executing the RT-4 packages P1-P8
   (sums to 2,698). The latest snapshot has **2,698/117,624 blocked
   entries**, 114,926 supported (58,950 staged), and one legacy-binary
   load error. This is static evidence only.
2. **RT-3 through RT-5:** close the binary-format, provider, address,
   AA, Lua host, and runtime behavior gaps with independent synthetic
   cases and owned-target tests. Pure visual Forms rendering (WP-42)
   is outside the requested trainer-behavior scope; any form control
   that causes a game-facing action remains in scope.
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
