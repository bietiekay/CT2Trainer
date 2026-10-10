# CT2Trainer: Native progress ledger

Status: **October 10, 2026** (0.9.0-rc2). This is the binding result list:
confirmed state, measured numbers, and the prioritized open work. The
plan (work packages, protocol) lives in
[`plans/native-implementation-continuation.md`](../plans/native-implementation-continuation.md);
code/build boundaries in
[`native-runtime.md`](native-runtime.md) and
[`native-verification.md`](native-verification.md).

## 1. Goal and acceptance contract

- **Feature-matrix goal: 100% coverage of the in-scope 0.9 feature set
  (AP-11 excluded) — REACHED 2026-10-10 and closed.** 39/39 in-scope
  features covered; 100% feature-weighted; 7332/7332 action-weighted over
  the pinned 5967-action corpus. The earlier 90% hurdle is subsumed.
- **Gates 1–3 are closed with real, tested evidence:**
  1. `gate:1` per-table completeness for all 13 pinned tables (Forms, Lua
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
- **AP-11 (observed real-game effect for all 5967 pinned actions)
  remains a separate end goal** — 0 confirmed so far — and is excluded
  from the 100% feature metric.
- **Final product acceptance** is separate on Windows (clean PC/VM, no
  CE/Python) and on a real Steam Deck under Proton with touch operation.
  `runtime_unverified` stays set until both pass.

## 2. Confirmed state (0.9.0-rc2)

| Item | Value |
| --- | --- |
| Repository baseline | `main` @ `b6c48cc` "initial 0.9 version" (self-contained clean-room tree) |
| Version | `0.9.0-rc2` (root `VERSION` file) |
| Test suite | **2617 OK / 25 expected skips** (in-build suite of the offline build) |
| Feature matrix | **39/39 covered** (100% feature-weighted, 7332/7332 action-weighted) — `gap_inventory/feature-coverage.json` |
| AP-11 manifest | 13 tables, 5967 expected actions, 0 confirmed, all consistency gates `all_ok` — `gap_inventory/ap11-campaign.json` |
| Latest verified build | `native-20261010T172336Z-ffe35eb0` via `scripts/Build-Native.ps1`: both ZIPs, in-build suite 2617/25, `ce_inputs: []`, `api-prototypes.json` present in both EXE payload inventories, `runtime_unverified` deliberately set |
| User-tested portable | run `native-20261010T165731Z-3d1da645`: converter run + generated trainer verified by the user on a machine without CE/Python |

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
from the committed corpus with a fixed run id:

```
python tools/corpus_denominator/__main__.py --corpus TableReferences --output gap_inventory --run-id repo-reproducible
python tools/corpus_denominator/feature_matrix.py --output gap_inventory --run-id repo-reproducible
python tools/corpus_denominator/ap11_campaign.py manifest --output gap_inventory --run-id repo-reproducible
```

The committed artifacts are the reference; gate:3
(`tests/test_native_repro_chain.py`) re-runs the full chain and compares.
Corpus: 13 synthetic case tables (`TableReferences/case-01.ct` …
`case-13.ct`, see `TableReferences/README.md` for the case-to-origin
mapping), 147 distinct SHA-256 hashes collapsed to 13 pinned cases,
5967 expected actions.

## 4. Prioritized open work

1. **AP-11 real-game campaign (the end goal).** Runbook:
   [`native-ap11-campaign.md`](native-ap11-campaign.md). Manifest + report
   ingestion tooling are ready (`ap11_campaign.py`). Suggested start:
   the small tables — case-05 (9, clock), case-03 (32, mono), case-04
   (25, IL2CPP), case-08 (16, typed calls) — before case-07 (5152
   actions). Each confirmed observation moves the campaign counter; the
   denominator document and campaign state stay under `gap_inventory/`.
2. **Final acceptance Windows (clean PC/VM, no CE/Python):** portable
   converter start, new trainer, Unicode paths, settings/state,
   notices/rights/UAC, debugger conflicts; full toggle/freeze/one-shot/
   value roundtrips including controller restart and saved-wish replay.
3. **Final acceptance Steam Deck:** real Proton prefix, touch operation,
   x86/x64 targets, screen keyboard, hotkeys, state/freeze/clock, exit
   behavior (protocol: `tests/deck/compatibility-matrix.md`).
4. **0.9.0 final release** after (1)–(3): bump `VERSION`, fresh offline
   build, record the observed build (versions, hashes, setup, result) in
   this ledger and `native-verification.md`, then flip
   `runtime_unverified`.
5. **Maintenance:** keep `runtime_unverified` honest; record every
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
