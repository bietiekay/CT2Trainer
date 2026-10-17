# CT2Trainer: Native progress ledger

**Central tracking:** all open gaps, goals, work packages, corpus cases and
the measurement snapshot are tracked in one place:
[`plans/TRACKING.md`](../plans/TRACKING.md). This ledger keeps the
confirmed-state detail (builds, suites, acceptance records); when in doubt
about current status, check the tracker first.

Status: **October 16, 2026** (0.11 released; reference-corpus closure
cycle on working branch `native-0.12`: Wave 2 closed — W2-A + W2-C +
W2-B merged, cases 15–18 pinned/extended, 20 pinned tables, plan
`plans/reference-closure-continuation.md`). This is the binding result list:
confirmed state, measured numbers, and the prioritized open work. The
plan (work packages, protocol) lives in
[`plans/native-implementation-continuation.md`](../plans/native-implementation-continuation.md);
code/build boundaries in
[`native-runtime.md`](native-runtime.md) and
[`native-verification.md`](native-verification.md).

## 1. Goal and acceptance contract

- **Feature-matrix goal: 100% coverage of the in-scope 0.9 feature set
  (AP-11 excluded) — REACHED 2026-10-10 and closed, extended by WP-14 on
  2026-10-11, extended by WP-27/32/33/34 (W2-A) on 2026-10-14, extended
  by WP-30/36 (W2-C) on 2026-10-15 and by WP-28/29/31/35 (W2-B) on
  2026-10-16.** 42/42 in-scope features covered (39 gap classes + 3
  gates); 100% feature-weighted; 7408/7408
  action-weighted over the pinned 6080-action corpus (20
  tables, run `w2b-case18-20261016142912Z`). The 2026-10-15 state (7387/7387 over
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
  1. `gate:1` per-table completeness for all 20 pinned tables (Forms, Lua
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
- **AP-11 (observed real-game effect for all 6080 pinned actions)
  remains a separate end goal** — 0 confirmed so far — and is excluded
  from the 100% feature metric.
- **Final product acceptance** is separate on Windows (clean PC/VM, no
  CE/Python) and on a real Steam Deck under Proton with touch operation.
  `runtime_unverified` stays set until both pass.

## 2. Confirmed state (0.9.0-rc2 + WP-14..36 + 0.12 build, 2026-10-16)

| Item | Value |
| --- | --- |
| Repository baseline | `main` @ `b6c48cc` "initial 0.9 version" (self-contained clean-room tree) |
| Version | `0.14` (root `VERSION` file; 0.9.0-rc2 was the last user-tested release) |
| Test suite | **2932 OK / 25 expected skips, 0 failures** (full local dev suite on `native-0.14` after the per-wish restore isolation and program-scan debug logging, verified 2026-10-17 at the canonical path; previously 2927 on `native-0.13` after the optional debug-logging feature incl. attach-failure dedupe and the module-snapshot fallback, verified 2026-10-16; previously 2925 after the debug-logging feature; previously 2910 after the W2-C + W2-B merges and the case-15 part 2 + case-18 pins; previously 2840 after the W2-A merge and the case-20 + case-16 + case-17 + case-15 pins, verified 2026-10-14; previously 2805 after the W1-A + W1-E merges and the case-20 + case-16 + case-15 pins; previously 2769 after the W1-D + W1-C + W1-B integration; previously 2710 after the WP-18 merge `9a76eb8`; previously 2698 after the WP-17 merge `557b2ac`; previously 2688 after the WP-15 merge `d3316aa`; previously 2679 on `native-l5-19` after the WP-16 merge `38a830d`; previously 2671 on `native-0.9-staged` after the WP-14 gate-test merge `54b172e`); in-build suite 2932/25 passed (0.14 build `native-20261017T115850Z-1ebb48b7`); previously 2927/25 (0.13 build `native-20261016T190005Z-b3139b30`); previously 2925/25 (superseded 0.13 build `native-20261016T181516Z-b8ae88de`); previously 2910/25 (0.12 build `native-20261016T163910Z-d047f2d2`); previously 2710/25 (0.11 build `native-20261012T092729Z-2d8aaf12`); previously 2698/25 (0.11 build `native-20261011T182033Z-f3317337`); previously 2671/25 (0.10 build `native-20261011T121914Z-bfc5fc11`) |
| Feature matrix | **42/42 covered** (100% feature-weighted, 7408/7408 action-weighted; run `w2b-case18-20261016142912Z`; previously 7387/7387, run `w2c-case15p2b-20261015144326Z`) — `gap_inventory/feature-coverage.json` |
| AP-11 manifest | 20 tables, 6080 expected actions, 0 confirmed, all consistency gates `all_ok` (run `w2b-case18-20261016142912Z`; previously 19 tables / 6062 actions) — `gap_inventory/ap11-campaign.json` |
| Latest verified build | `native-20261017T115850Z-1ebb48b7` (0.14) via `scripts/Build-Native.ps1` from `main` @ `fca6b06` (2026-10-17): both ZIPs (`CT2Trainer-0.14-source.zip` sha256 `a5b075cf…`, `CT2Trainer-0.14-windows-portable.zip` sha256 `e57fe9b9…`), in-build suite 2932 OK / 25 expected skips, `ce_inputs: []`, `runtime_unverified` deliberately set, source inputs unchanged; both ZIPs carry the elaborated release READMEs (portable guide includes the debug-logging section) and the changelog with the 0.14 + 0.13 + 0.12 entries. 0.14 adds per-wish restore isolation (a `ScanMiss` in one saved record no longer blocks the engine) and per-scan debug logging for program (AA script) preflight scans. Previous: `native-20261016T190005Z-b3139b30` (0.13, in-build 2927/25); `native-20261016T181516Z-b8ae88de` (0.13 pre module-snapshot fallback, in-build 2925/25); `native-20261016T163910Z-d047f2d2` (0.12, in-build 2910/25); `native-20261016T161905Z-e8ef67a0` (0.12, byte-identical re-cut); `native-20261016T154141Z-2de774ab` (0.12 pre release-docs); `native-20261012T092729Z-2d8aaf12` (0.11, in-build 2710/25); `native-20261011T121914Z-bfc5fc11` (0.10, in-build 2671/25); `native-20261010T172336Z-ffe35eb0` (rc2, in-build 2617/25, `api-prototypes.json` present in both EXE payload inventories, user-tested portable) |
| User-tested portable | run `native-20261010T165731Z-3d1da645`: converter run + generated trainer verified by the user on a machine without CE/Python |
| Reference-corpus assessment (2026-10-13) | 151 local-only reference tables: baseline 117,019 plan entries, 95,167 supported (incl. 46,987 staged), **21,852 blocked**, 4 whole-table compile errors (run `ref-assessment`); after W1-D (WP-25) + W1-C (WP-22/23): **21,851 of 117,255 blocked**, 3 whole-table compile errors — Octopath compiles (227 supported / 9 blocked, 24 duplicate-ID warnings), 20XX fully supported (10/10), SuperMeatBoy refused with a named legacy-binary error (catalog re-run 2026-10-13); after W1-B + W1-A + W1-E: **10,892 of 117,624 blocked**, 1 whole-table compile error (SuperMeatBoy legacy binary only; AtomicHeart `$process` closed by WP-19, Cyberpunk `@@` by WP-20) (catalog re-run 2026-10-14); after W2-A (WP-27/32/33/34): **9,962 of 117,624 blocked**, 1 whole-table compile error (SuperMeatBoy only; catalog re-run 2026-10-14, `blocked-catalog-w2a.json`; −930 blocked, 0 supported regressions, +197 previously masked records now surface the named missing-target reason); after W2-B + W2-C (WP-28/29/31/35 + WP-30/36): **7,577 of 117,624 blocked** (−2,385, 0 supported regressions; 1 whole-table compile error, SuperMeatBoy only; catalog re-run 2026-10-16, `blocked-catalog-w2final.json`); consolidated assessment `documentation/reference-gap-assessment.md`, closure plan `plans/reference-closure-continuation.md` (WP-19…WP-42) |

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
Corpus: 20 synthetic case tables (`TableReferences/case-01.ct` …
`case-14.ct`, `case-15.ct`, `case-16.ct`, `case-17.ct`, `case-18.ct`,
`case-19.ct`, `case-20.ct`; case-to-origin mapping in
`TableReferences/README.md`), 143 distinct SHA-256 hashes collapsed to
20 pinned cases, 6080 expected actions (run
`w2b-case18-20261016142912Z`).

## 4. Prioritized open work

1. **Reference-corpus closure campaign (active since 2026-10-13, cycle
   branch `native-0.12`).** The 151-table local-only reference corpus
   leaves **7,577 of 117,624 entries blocked**
   (110,047 supported incl. 54,234 staged;
   1 whole-table compile error; after W2-B + W2-C,
   2026-10-16; baseline 21,852 of 117,019 with 4) — consolidated
   assessment: `documentation/reference-gap-assessment.md`; work
   packages WP-19…WP-42 (waves, dependencies, derivative corpus cases
   case-15…case-25, catalog-re-run acceptance protocol):
   `plans/reference-closure-continuation.md`. Best-case closure ≈ 85 %
   of the blocked entries; residue is documented fail-closed.
2. **AP-11 real-game campaign (the end goal).** Runbook:
   [`native-ap11-campaign.md`](native-ap11-campaign.md). Manifest + report
   ingestion tooling are ready (`ap11_campaign.py`). Suggested start:
   the small tables — case-05 (9, clock), case-03 (32, mono), case-04
   (25, IL2CPP), case-08 (16, typed calls) — before case-07 (5152
   actions). Each confirmed observation moves the campaign counter; the
   denominator document and campaign state stay under `gap_inventory/`.
3. **Final acceptance Windows (clean PC/VM, no CE/Python):** portable
   converter start, new trainer, Unicode paths, settings/state,
   notices/rights/UAC, debugger conflicts; full toggle/freeze/one-shot/
   value roundtrips including controller restart and saved-wish replay.
4. **Final acceptance Steam Deck:** real Proton prefix, touch operation,
   x86/x64 targets, screen keyboard, hotkeys, state/freeze/clock, exit
   behavior (protocol: `tests/deck/compatibility-matrix.md`).
5. **Release closure (0.11 current)** after (2)–(4): the 0.11 build
   `native-20261012T092729Z-2d8aaf12` is cut from `main`; record
   the observed build (versions, hashes, setup, result) from the
   acceptance runs in this ledger and `native-verification.md`, then flip
   `runtime_unverified`.
6. **Maintenance:** keep `runtime_unverified` honest; record every
   Windows/Deck observation with build id, hashes, setup and result
   before raising the status.

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
