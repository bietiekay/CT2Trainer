# CT2Trainer: Native progress ledger

**Central tracking:** all open gaps, goals, work packages, corpus cases and
the measurement snapshot are tracked in one place:
[`plans/TRACKING.md`](../plans/TRACKING.md). This ledger keeps the
confirmed-state detail (builds, suites, acceptance records); when in doubt
about current status, check the tracker first.

Status: **October 24, 2026** (0.16.4 released, build
`native-20261024T003853Z-a8cf04fc` cut from `main` @ `988ff8e` - the
0.16.4 field fix (Sinking City 2 trainer crash observability from the
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

## 2. Confirmed state (0.9.0-rc2 + WP-14..58 + 0.16 field-fix re-cut 2 + 0.16.1/0.16.2/0.16.3/0.16.4 field fixes + RT-4.1 + RT-3 + RT-4.4 + RT-5 inventory, 2026-10-24)

| Item | Value |
| --- | --- |
| Repository baseline | `main` @ `b6c48cc` "initial 0.9 version" (self-contained clean-room tree) |
| Version | `0.16.4` (root `VERSION` file; 0.9.0-rc2 was the last user-tested release, 0.16 user-tested 2026-10-20 with the WP-58 startup crash, fix in the re-cut; 0.16.1/0.16.2/0.16.3 field-tested 2026-10-21/22/23, 0.16.4 crash-observability field fix awaiting field test) |
| Test suite | **3479 OK / 25 expected skips, 0 failures** (full local dev suite on the `native-0.16.4-sc2-field` branch after the 0.16.4 trainer-crash-observability field fix - `tests/test_native_sc2_crash_observability.py` +8: crash hooks (excepthook/threading/faulthandler), poll guard, restore-entry-start ordering, verified 2026-10-24 at the canonical path with CT2TRAINER_NASM set; previously 3471 OK / 25 expected skips, 0 failures (full local dev suite on `main` after the RT-4.4 value-semantics merge - O6/O8 dropdown width truncation + expression choices per the CE SetValue conclusions, O7 ShowAsHex strings staged as byte_array profiles, O26 empty/placeholder-only read-only dropdowns staged as display-only views, O11 custom-type gate kept by design (`tests/test_native_value_semantics.py` +18 plus pin updates in dropdown/value/compiler/engine modules), verified 2026-10-23 at the canonical path with CT2TRAINER_NASM set; previously 3450 OK / 25 expected skips, 0 failures (full local dev suite on `main` after the RT-3 legacy-binary CT loader merge — clean-room parser `src/ct2trainer/legacy_ct.py`, +28 `tests/test_native_legacy_ct.py`, updated legacy pins in `tests/test_native_table_robustness.py`, verified 2026-10-23 at the canonical path with CT2TRAINER_NASM set; previously 3421 OK / 25 expected skips, 0 failures (full local dev suite on `main` after the 0.16.3 field fix - hook-journal `value_data_ranges` accepted by the recovery assessment + module-snapshot transient retry with backoff (`tests/test_native_architecture.py` +4, `tests/test_native_recovery.py` +2), verified 2026-10-23 at the canonical path with CT2TRAINER_NASM set; previously 3415 OK / 25 expected skips, 0 failures (full local dev suite on `main` after the RT-4.1 symbol provider fidelity merge — keep-first duplicate-provider policy, `label()` duplicate-name tolerance, wildcard-cleanup scoping (nine focused modules, 167 tests, incl. `tests/test_native_provider_selection_dedupe.py`), verified 2026-10-22 at the canonical path with CT2TRAINER_NASM set; previously 3414 OK / 25 expected skips, 0 failures (full local dev suite on `main` after the 0.16.2 field fix — WP-57 hook journal `captured_placeholders` accepted by the recovery assessment (`tests/test_native_recovery.py`, +2 tests), verified 2026-10-22 at the canonical path with CT2TRAINER_NASM set; previously 3412 OK / 25 expected skips, 0 failures (full local dev suite on `main` after the 0.16.1 SC2 table-load warning fix — table-version reference 45 → 46 + accurate `{$LUA}`/external-action warnings (`tests/test_native_sc2_table_warnings.py`, version assertion in `tests/test_native_compiler.py`), verified 2026-10-21 at the canonical path with CT2TRAINER_NASM set; previously 3405 on `main` after the 0.16 field-fix round 2 — state-lock self-repair and reliable restart (`tests/test_native_stale_lock_selfheal.py`, updated variant-close assertion in `tests/test_native_engine.py`), verified 2026-10-21 at the canonical path with CT2TRAINER_NASM set; previously 3398 on `main` after the 0.16 field-fix cycle — WP-58 UI startup crash fix + Sinking City 2 runtime chain evidence (`tests/test_native_ui_button.py`, `tests/test_native_sc2_attach_chain.py`), verified 2026-10-20 at the canonical path with CT2TRAINER_NASM set; previously 3393 on `main` after the W4 B4 merges and the case-28/29/30 pins, verified 2026-10-20 at the canonical path; previously 3233 on `main` after the W4 cycle merge and the case-26/27/31 pins, verified 2026-10-19 at the canonical path; previously 3057 on `native-0.15` after the W3 batch 1 + batch 2 + batch 3 + batch 4 merges (WP-39/40/38/41/37) and the case-23 + case-21 + case-22 + case-24 pins, verified 2026-10-18; previously 3046 after the W3 batch 3 merge (WP-41) and the case-22 pin; previously 3001 after the W3 batch 1 + batch 2 merges (WP-39/40/38) and the case-23 + case-21 pins, verified 2026-10-18 at the canonical path; previously 2943 after the 0.15 prefix-cut field fix at `d15268a`, 2026-10-17; previously 2932 on `native-0.14` after the per-wish restore isolation and program-scan debug logging, verified 2026-10-17 at the canonical path; previously 2927 on `native-0.13` after the optional debug-logging feature incl. attach-failure dedupe and the module-snapshot fallback, verified 2026-10-16; previously 2925 after the debug-logging feature; previously 2910 after the W2-C + W2-B merges and the case-15 part 2 + case-18 pins; previously 2840 after the W2-A merge and the case-20 + case-16 + case-17 + case-15 pins, verified 2026-10-14; previously 2805 after the W1-A + W1-E merges and the case-20 + case-16 + case-15 pins; previously 2769 after the W1-D + W1-C + W1-B integration; previously 2710 after the WP-18 merge `9a76eb8`; previously 2698 after the WP-17 merge `557b2ac`; previously 2688 after the WP-15 merge `d3316aa`; previously 2679 on `native-l5-19` after the WP-16 merge `38a830d`; previously 2671 on `native-0.9-staged` after the WP-14 gate-test merge `54b172e`); in-build suite 2932/25 passed (0.14 build `native-20261017T115850Z-1ebb48b7`); previously 2927/25 (0.13 build `native-20261016T190005Z-b3139b30`); previously 2925/25 (superseded 0.13 build `native-20261016T181516Z-b8ae88de`); previously 2910/25 (0.12 build `native-20261016T163910Z-d047f2d2`); previously 2710/25 (0.11 build `native-20261012T092729Z-2d8aaf12`); previously 2698/25 (0.11 build `native-20261011T182033Z-f3317337`); previously 2671/25 (0.10 build `native-20261011T121914Z-bfc5fc11`) |
| Feature matrix | **42/42 covered** (100% feature-weighted, 7475/7475 action-weighted; run `w4b4-case30-20261020081722Z`; previously 7446/7446, run `w4-case31-20261019061339`; previously 7426/7426, run `w3e-case24-20261018051230`; previously 7416/7416, run `w3d-case22-20261018040510`; previously 7413/7413, run `w3b-case21-20261018023823Z`; previously 7411/7411, run `w3-case23-20261018012531Z`) — `gap_inventory/feature-coverage.json` |
| AP-11 manifest | 30 tables, 6143 expected actions, 0 confirmed, all consistency gates `all_ok` (run `w4b4-case30-20261020081722Z`; previously 27 tables / 6119 actions, previously 24 tables / 6100 actions, previously 23 tables / 6092 actions) — `gap_inventory/ap11-campaign.json` |
| Latest verified build | `native-20261024T003853Z-a8cf04fc` (0.16.4) via `scripts/Build-Native.ps1` from `main` @ `988ff8e` (2026-10-24): both ZIPs (`CT2Trainer-0.16.4-source.zip` sha256 `87e1f448`, `CT2Trainer-0.16.4-windows-portable.zip` sha256 `ffa08832`), in-build suite 3479 OK / 25 expected skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per gate; both ZIPs carry the changelog with the 0.16.4 + 0.16.3 + 0.16.2 + 0.16.1 + 0.16 + 0.15 + 0.14 entries. 0.16.4 ships the Sinking City 2 trainer-crash-observability field fix (crash hooks + faulthandler sink into the opt-in debug log, fail-closed poll guard, `restore-entry-start` markers, `tests/test_native_sc2_crash_observability.py` +8) on top of the 0.16.3 content and the RT-4.4 value-semantics merge (catalog remeasure `blocked-catalog-rt44`: 1,858 -> 1,807 blocked of 117,634, zero newly blocked rows). Superseded 0.16.3 build: `native-20261023T065015Z-afbc3eba` (0.16.3) via `scripts/Build-Native.ps1` from `main` @ `6a5ba63` (2026-10-23): both ZIPs (`CT2Trainer-0.16.3-source.zip` sha256 `0b34c4f3`, `CT2Trainer-0.16.3-windows-portable.zip` sha256 `bb495a6f`), in-build suite 3421 OK / 25 expected skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per gate; both ZIPs carry the changelog with the 0.16.3 + 0.16.2 + 0.16.1 + 0.16 + 0.15 + 0.14 entries. 0.16.3 ships the Sinking City 2 activation field fix (recovery assessment accepts the hook-journal `value_data_ranges` allocation field; module-snapshot transient retry with correct Win32 codes, bounded exponential backoff, architecture-aware fallback flag; regression tests `tests/test_native_architecture.py` +4, `tests/test_native_recovery.py` +2) on top of the 0.16.2 content. Superseded 0.16.2 build: `native-20261022T160328Z-0423fb21` (0.16.2) via `scripts/Build-Native.ps1` from `main` @ `68eeb00` (2026-10-22): both ZIPs (`CT2Trainer-0.16.2-source.zip` sha256 `1e284d2a…`, `CT2Trainer-0.16.2-windows-portable.zip` sha256 `9c8ccc9e…`), in-build suite 3415 OK / 25 expected skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per gate; both ZIPs carry the changelog with the 0.16.2 + 0.16.1 + 0.16 + 0.15 + 0.14 entries. 0.16.2 ships the Sinking City 2 startup-block field fix (recovery assessment accepts the WP-57 hook-journal `captured_placeholders` field, regression tests `tests/test_native_recovery.py`) and RT-4.1 symbol provider fidelity (keep-first duplicate-provider policy, `label()` duplicate-name tolerance, wildcard-cleanup scoping; catalog remeasure 2,698 -> 1,858 blocked of 117,624, zero unexplained supported regressions) on top of the 0.16.1 content. Superseded 0.16.1 build: `native-20261021T161241Z-b0566a25` (0.16.1, first build under the new versioning rule, cut from `main` @ `d1c61f2`; in-build 3412/25, `ce_inputs: []`, user-tested, field finding: Sinking City 2 startup block). 0.16.1 ships the SC2 table-load warning fixes (table-version reference 45 → 46 field-verified; `{$LUA}` warning states the built-in Lua runtime path; external-action warning split per API — ShellExecute safe no-op, messageDialog review flag) on top of the 0.16 content. 0.16 ships the full Wave 4 feature set (WP-43…WP-57 + WP-58 UI) plus the post-release field fixes (WP-58 UI startup crash fix + Sinking City 2 activation-chain runtime evidence + state-lock self-repair and reliable restart) on top of the released 0.15 content. Superseded 0.16 runs: `native-20261021T141051Z-17d53c1d` (0.16, cut from `main` @ `e9f06fb` after the RT-1 rebaseline, in-build 3405/25, `ce_inputs: []`, superseded by the 0.16.1 cut before its evidence was recorded), `native-20261021T123801Z-8c5c4e1e` (0.16 field-fix re-cut 2, cut from `main` @ `108170b`, in-build 3405/25, user-tested, field finding: Sinking City 2 table-load warnings), `native-20261020T150115Z-c426fb92` (cut from `main` @ `7616edb`, in-build 3398/25, user-tested, field findings: one cheat = table/build mismatch, state-lock orphan after a blocked close) and `native-20261020T103508Z-0e3f9d90` (cut from `main` @ `809666a`, in-build 3393/25, user-tested, shipped with the WP-58 UI startup crash). Previous: `native-20261018T055505Z-39f20180` (0.15) via `scripts/Build-Native.ps1` from `main` @ `ed0b97b` (2026-10-18): both ZIPs (`CT2Trainer-0.15-source.zip` sha256 `5d5a85f6…`, `CT2Trainer-0.15-windows-portable.zip` sha256 `cfcc8e06…`), in-build suite 3057 OK / 25 expected skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per gate; both ZIPs carry the elaborated release READMEs and the changelog with the 0.15 + 0.14 + 0.13 entries. 0.15 ships the prefix-cut byte-patch validation (the 0.14-ext2 Great Circle field finding: Stealth Mode and No Reload use `db 90 E9` over a 6-byte conditional jump, now proven at link time and re-verified at stage time) plus the full Wave 3 feature set on top of the 0.14 content. Previous: `native-20261017T115850Z-1ebb48b7` (0.14, in-build 2932/25); `native-20261016T190005Z-b3139b30` (0.13, in-build 2927/25); `native-20261016T181516Z-b8ae88de` (0.13 pre module-snapshot fallback, in-build 2925/25); `native-20261016T163910Z-d047f2d2` (0.12, in-build 2910/25); `native-20261016T161905Z-e8ef67a0` (0.12, byte-identical re-cut); `native-20261016T154141Z-2de774ab` (0.12 pre release-docs); `native-20261012T092729Z-2d8aaf12` (0.11, in-build 2710/25); `native-20261011T121914Z-bfc5fc11` (0.10, in-build 2671/25); `native-20261010T172336Z-ffe35eb0` (rc2, in-build 2617/25, `api-prototypes.json` present in both EXE payload inventories, user-tested portable) |
| User-tested portable | run `native-20261010T165731Z-3d1da645`: converter run + generated trainer verified by the user on a machine without CE/Python |
| Reference-corpus assessment (2026-10-13) | 151 local-only reference tables: baseline 117,019 plan entries, 95,167 supported (incl. 46,987 staged), **21,852 blocked**, 4 whole-table compile errors (run `ref-assessment`); after W1-D (WP-25) + W1-C (WP-22/23): **21,851 of 117,255 blocked**, 3 whole-table compile errors — Octopath compiles (227 supported / 9 blocked, 24 duplicate-ID warnings), 20XX fully supported (10/10), SuperMeatBoy refused with a named legacy-binary error (catalog re-run 2026-10-13); after W1-B + W1-A + W1-E: **10,892 of 117,624 blocked**, 1 whole-table compile error (SuperMeatBoy legacy binary only; AtomicHeart `$process` closed by WP-19, Cyberpunk `@@` by WP-20) (catalog re-run 2026-10-14); after W2-A (WP-27/32/33/34): **9,962 of 117,624 blocked**, 1 whole-table compile error (SuperMeatBoy only; catalog re-run 2026-10-14, `blocked-catalog-w2a.json`; −930 blocked, 0 supported regressions, +197 previously masked records now surface the named missing-target reason); after W2-B + W2-C (WP-28/29/31/35 + WP-30/36): **7,577 of 117,624 blocked** (−2,385, 0 supported regressions; 1 whole-table compile error, SuperMeatBoy only; catalog re-run 2026-10-16, `blocked-catalog-w2final.json`); after W4 B1–B3 (WP-43/44, WP-46 part 1, WP-47/55, WP-45/56, WP-51/48, WP-52): **3,632 of 117,624 blocked** (−3,945, supported 113,992 incl. 58,018 staged; 1 whole-table compile error, SuperMeatBoy only; catalog re-run 2026-10-19, `blocked-catalog-w4final.json`); after W4 B4 (WP-46 part 2, WP-49/50, WP-53/54, WP-57, WP-58): **2,698 of 117,624 blocked** (−934, supported 114,926 incl. 58,950 staged; 1 whole-table compile error, SuperMeatBoy only; catalog re-run 2026-10-20, `blocked-catalog-w4b4.json`); after RT-4.1 (symbol provider fidelity, 2026-10-22): **1,858 of 117,624 blocked** (net −840: 842 unblocked, 2 explained Cyberpunk shared-global regressions; supported 115,766 incl. 59,642 staged; 1 whole-table compile error, SuperMeatBoy only; catalog re-run `blocked-catalog-rt41`); after RT-3 (legacy-binary CT loader, 2026-10-23): **1,858 of 117,634 blocked**, **151/151 tables load** (the last whole-table load error cleared; `SuperMeatBoy.CT` now compiles to 10 supported / 0 staged / 0 blocked records; the other 150 tables byte-identical per-table; supported 115,776 incl. 59,642 staged; catalog re-run `blocked-catalog-rt3`); after RT-4.4 (value semantics, 2026-10-23): **1,807 of 117,634 blocked** (net -51 vs `blocked-catalog-rt3`: O6/O7/O8/O26 value-semantics rows cleared, zero newly blocked, 8 rows reason-changed onto pre-existing symbol-provider blocks; supported 115,827 incl. 59,683 staged; 151/151 load; catalog re-run `blocked-catalog-rt44`); consolidated assessment `documentation/reference-gap-assessment.md`, closure plan `plans/archive/reference-closure-continuation.md` (WP-19…WP-42) |

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
- **Known root-owned defect (out of lane scope):** the pinned NASM 3.02
  dependency mis-encodes the FSTP fpureg table entry —
  `x86/insns.dat` line 751 `FSTP fpureg [r: dd d8+r]` instead of
  `df c0+r`. Measured: `fstp st0` -> `DD D8`, `fstp st1` -> `DD D9`
  (both wrong; expected `DF C0` / `DF C1`), while `fcomip st0, st1` ->
  `DF F1` is correct. NASM 3.02 also rejects the parenthesized
  `st(N)` syntax outright (bare `st0`-`st7` only), which the tokenizer
  fold works around at link time. Consequence: the two Witcher3
  `fstp st(0)` rows (one per 4.0x table) pass our linker but assemble
  with wrong bytes until root re-pins or locally patches the NASM
  dependency (authorized local-fork/adaptation path per `AGENTS.md`,
  with source pin, notice and build evidence).

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
   2026-10-24, RT-4.6 done 2026-10-24, RT-5 inventory done 2026-10-23):**
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
   see the RT-4.5 section above). Next: executing the remaining RT-4
   packages RT-4.3 452, RT-4.2 1,085 last. The latest snapshot has
   **1,743/117,634 blocked entries**, 115,891 supported (59,735
   staged), and zero load errors (run `blocked-catalog-rt45main`). This
   is static evidence only.
2. **RT-4.x through RT-5:** close the remaining address, value, AA
   directive, input-legacy and runtime-provider gaps (RT-4.x) and the
   RT-5 implementation items A-G inventoried in
   `documentation/rt5-api-inventory.md` (embedded-file loader contract,
   bounded process-info APIs, table-callback dispatch, CheatCodes
   code patches, messageDialog decision, no-effect register, thread
   backend) with independent synthetic cases and owned-target tests.
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
