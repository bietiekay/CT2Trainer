# CT2Trainer Native verification

Status: October 20, 2026 (0.16; release build `native-20261020T150115Z-c426fb92`, cut from `main` @ `7616edb`).

This document records the **current** verification state of the
independent CT2Trainer Native edition: what is proven, how it is
reproduced, and what remains open. Per-run evidence lives in the local
build run folders (`build/runs/native-<UTC-timestamp>-<id>/`) and is not
committed.

The feature matrix covers 42/42 in-scope features over the 30-table synthetic corpus; that result does not establish support for the full real reference corpus or real-game behavior. The local-only full-reference static catalog still has 2,698 of 117,624 plan entries blocked. AP-11 has 0 confirmed real-game actions, and runtime acceptance remains `runtime_unverified: true`.

## 1. Current baseline

| Item | Value |
| --- | --- |
| Release version | `0.9.0-rc2` released; `0.16` in the root `VERSION` file, build `native-20261020T150115Z-c426fb92` (field-fix re-cut) cut from `main` @ `7616edb` (2026-10-20); previous 0.16 run `native-20261020T103508Z-0e3f9d90` (superseded, pre field-fix, user-tested); previous `0.15` build `native-20261018T055505Z-39f20180` cut from `main` @ `ed0b97b` (2026-10-18); previous `0.14` build `native-20261017T115850Z-1ebb48b7` cut from `main` @ `fca6b06` (2026-10-17); previous `0.13` build `native-20261016T190005Z-b3139b30` cut from `main` @ `d57e62c` (2026-10-16); previous 0.13 run `native-20261016T181516Z-b8ae88de` (superseded, pre module-snapshot fallback); previous `0.12` build `native-20261016T163910Z-d047f2d2` cut from `main` @ `ba1d3e4` (2026-10-16); previous `0.11` build `native-20261012T092729Z-2d8aaf12` cut from `main` @ `9a76eb8` (2026-10-12) |
| Build entry point | `scripts/Build-Native.ps1` (fully offline, no network) |
| Full native suite | **3398 OK / 25 expected skips, 0 failures** (full local dev suite on `main` after the 0.16 field-fix cycle — WP-58 UI startup crash fix + Sinking City 2 activation-chain runtime evidence — verified 2026-10-20 at the canonical path with CT2TRAINER_NASM set; previously 3393 on `main` after the W4 B4 merges and the case-28/29/30 pins, verified 2026-10-20 at the canonical path; previously 3233 on `main` after the W4 cycle merge and the case-26/27/31 pins, verified 2026-10-19 at the canonical path; previously 3057 on `native-0.15` after the W3 batch 4 merge (WP-37) and the case-24 pin, verified 2026-10-18 at the canonical path, and the in-build suite of the 0.15 cut `ed0b97b`; previously 3046 after the W3 batch 3 merge (WP-41) and the case-22 pin; previously 3001 after the W3 batch 1 + batch 2 merges (WP-39/40/38) and the case-23 + case-21 pins; previously 2943 after the 0.15 prefix-cut field fix `d15268a`; previously 2932 on `main` at the 0.14 cut `fca6b06`, verified 2026-10-17 at the canonical path; previously 2927 on `main` at the 0.13 cut `d57e62c`, verified 2026-10-16; previously 2925 after the debug-logging feature; previously 2910 after the W2-C + W2-B merges and the case-15 part 2 + case-18 pins; previously 2698 after the WP-17 merge `557b2ac`, verified 2026-10-11; previously 2688 after the WP-15 merge `d3316aa`; previously 2679 after the WP-16 merge `38a830d`; previously 2671 on `native-0.9-staged` after the WP-14 gate-test merge `54b172e`); in-build suite 3398/25 passed (build `native-20261020T150115Z-c426fb92`); previously 3393/25 passed (build `native-20261020T103508Z-0e3f9d90`, superseded by the field-fix re-cut); previously 3057/25 passed (build `native-20261018T055505Z-39f20180`); previously 2932/25 (build `native-20261017T115850Z-1ebb48b7`); previously 2927/25 (build `native-20261016T190005Z-b3139b30`); previously 2925/25 (superseded 0.13 build `native-20261016T181516Z-b8ae88de`); previously 2910/25 (build `native-20261016T163910Z-d047f2d2`); previously 2710/25 (build `native-20261012T092729Z-2d8aaf12`); previously 2698/25 (build `native-20261011T182033Z-f3317337`); previously 2671/25 (build `native-20261011T121914Z-bfc5fc11`) |
| CE inputs in the build | none (`ce_inputs: []` in `build.json`) |
| Runtime acceptance | `runtime_unverified: true`, deliberately kept |
| Corpus denominator | 6,143 expected actions, 1,291 groups (30 pinned case tables, run `w4b4-case30-20261020081722Z`) |
| Feature matrix | 42/42 in-scope features; 100% feature-weighted; 7475/7475 action-weighted (run `w4b4-case30-20261020081722Z`) |

The committed baselines under `gap_inventory/` carry the run stamp
`w4b4-case30-20261020081722Z` and are reproduced byte-for-byte by the
chain in section 4.

## 2. Offline build

From the repository root:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\Build-Native.ps1
```

Each run:

1. verifies the archived build inputs against `dependencies/manifest.json`
   (SHA-256 checked, no network access);
2. creates a fresh venv and installs PyInstaller, Lupa 2.8 and
   iced-x86 1.21.0 offline from `dependencies/`;
3. restores the pinned NASM 3.02 into the run folder;
4. runs the full native test suite (`suite-tests.log` / `suite-tests.json`
   with the tested source hashes);
5. freezes `CT2Trainer-Converter.exe` and `CT2Trainer-Template.exe` and
   audits both payload inventories (foreign-trainer module/payload
   tokens fail the build);
6. writes `build.json`, `payload-inventory.json`,
   `CT2Trainer-<version>-source.zip` and
   `CT2Trainer-<version>-windows-portable.zip` into the run folder.

A green build proves structure, input integrity and offline
reproducibility; it deliberately does **not** clear
`runtime_unverified`.

## 3. Verification gates (closed with tested evidence)

| Gate | Evidence |
| --- | --- |
| Per-table completeness for all 30 pinned synthetic case tables (Forms, table-Lua lifecycle, Custom Types, Assets; including WP-14 staged capabilities and the later Wave 4 cases) | `tests/test_native_table_completeness.py` |
| Source-to-Frozen parity of the 0.9 feature set, plus the binary CLI/GUI adapter for the static IL2CPP parser | `tests/test_native_source_frozen_parity.py`, `tests/test_native_il2cpp_static_probe.py` |
| End-to-end reproducibility chain (denominator -> feature matrix -> AP-11 manifest, byte-identical per fixed run-id) | `tests/test_native_repro_chain.py` |

Gate action weights remain 0: they are completeness/proof features, not
record actions. The AP-11 campaign (6,143 expected actions, 0 confirmed
real-game effect so far) is a separate end goal and is excluded from the
100% feature metric. The synthetic-corpus result does not establish full real-reference-corpus support; the local-only static catalog still has 2,698 of 117,624 plan entries blocked.

## 4. Reproduction commands

Full offline build:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\Build-Native.ps1
```

Local test suite (development venv per `build.md`):

```powershell
python tools/native_build.py restore-nasm --output .tools/native-tools
$env:PYTHONPATH="src;tests"
$env:PYTHONIOENCODING="utf-8"
$env:CT2TRAINER_NASM=(Resolve-Path .tools/native-tools/nasm.exe).Path
& .tools\native-build-env\Scripts\python.exe -m unittest discover -s tests -p test_native_*.py -q
```

Deterministic measurement chain (byte-identical for the fixed run-id
`repo-reproducible`). Stages 2 and 3 refuse to write into the directory
containing their inputs, so each uses a scratch output directory; stage 3
consumes the committed `gap_inventory/feature-coverage.json` so its
provenance stays byte-stable:

```powershell
python tools/corpus_denominator/__main__.py --corpus TableReferences --output gap_inventory --run-id repo-reproducible
python tools/corpus_denominator/feature_matrix.py --gap-report gap_inventory/gap-report.json --inventory gap_inventory/inventory.json --output <scratch2> --run-id repo-reproducible
copy <scratch2>/feature-coverage.json gap_inventory/feature-coverage.json
python tools/corpus_denominator/ap11_campaign.py manifest --gap-report gap_inventory/gap-report.json --inventory gap_inventory/inventory.json --feature-coverage gap_inventory/feature-coverage.json --corpus-root TableReferences --output <scratch3> --run-id repo-reproducible
copy <scratch3>/ap11-campaign.json gap_inventory/ap11-campaign.json
python -m unittest tests.test_native_repro_chain
```

Static IL2CPP probe (source CLI, read-only report):

```powershell
$env:PYTHONPATH="src"
python -m ct2trainer.native il2cpp <pe> --metadata <metadata-file> --output <report.json>
```

Windows fixture target (first Windows function gate):

```bat
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tests\windows\fixture_target\Invoke-FixturePreflight.ps1 -Compiler MSVC
```

## 5. What is still open

- **Runtime acceptance** stays `runtime_unverified: true` until
  separately measured:
  - a real Windows run against a game process (see the
    [fixture manual](../tests/windows/fixture_target/README.md)), and
  - the Steam Deck / Proton protocol (see the
    [compatibility matrix](../tests/deck/compatibility-matrix.md)).
- **AP-11**: 0 of 6,143 expected actions confirmed with observed
  real-game effect.
- Broad automatic table forms, remote speed control and managed
  invocation remain in development (see
  [`native-runtime.md`](native-runtime.md)).

Fixture tests and a green build never establish game compatibility.
After new Windows or Deck tests, record the observed build (versions,
hashes, test setup, result) here before raising any status.
