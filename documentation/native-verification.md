# CT2Trainer Native verification

Status: October 11, 2026 (0.9.0-rc2 baseline + WP-14 staged
capabilities, in cycle on `native-0.9-staged`).

This document records the **current** verification state of the
independent CT2Trainer Native edition: what is proven, how it is
reproduced, and what remains open. Per-run evidence lives in the local
build run folders (`build/runs/native-<UTC-timestamp>-<id>/`) and is not
committed.

## 1. Current baseline

| Item | Value |
| --- | --- |
| Release version | `0.9.0-rc2` released; `0.12` in the root `VERSION` file, build `native-20261016T163910Z-d047f2d2` cut from `main` @ `ba1d3e4` (2026-10-16); previous `0.11` build `native-20261012T092729Z-2d8aaf12` cut from `main` @ `9a76eb8` (2026-10-12) |
| Build entry point | `scripts/Build-Native.ps1` (fully offline, no network) |
| Full native suite | **2910 OK / 25 expected skips, 0 failures** (full local dev suite on `main` at the 0.12 cut `ba1d3e4`, verified 2026-10-16 at the canonical path; previously 2910 on `native-0.12` after the W2-C + W2-B merges and the case-15 part 2 + case-18 pins; previously 2698 after the WP-17 merge `557b2ac`, verified 2026-10-11; previously 2688 after the WP-15 merge `d3316aa`; previously 2679 after the WP-16 merge `38a830d`; previously 2671 on `native-0.9-staged` after the WP-14 gate-test merge `54b172e`); in-build suite 2910/25 passed (build `native-20261016T163910Z-d047f2d2`); previously 2710/25 (build `native-20261012T092729Z-2d8aaf12`); previously 2698/25 (build `native-20261011T182033Z-f3317337`); previously 2671/25 (build `native-20261011T121914Z-bfc5fc11`) |
| CE inputs in the build | none (`ce_inputs: []` in `build.json`) |
| Runtime acceptance | `runtime_unverified: true`, deliberately kept |
| Corpus denominator | 6,080 expected actions, 1,287 groups (20 pinned case tables, run `w2b-case18-20261016142912Z`) |
| Feature matrix | 42/42 in-scope features; 100% feature-weighted; 7408/7408 action-weighted (run `w2b-case18-20261016142912Z`) |

The committed baselines under `gap_inventory/` carry the run stamp
`w2b-case18-20261016142912Z` and are reproduced byte-for-byte by the
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
| Per-table completeness for all 14 pinned case tables (Forms, table-Lua lifecycle, Custom Types, Assets; the WP-14 staged case-14 adds signed-offset parents, script-parent cascades, staged leaf values and a record-ID activation set) | `tests/test_native_table_completeness.py` |
| Source-to-Frozen parity of the 0.9 feature set, plus the binary CLI/GUI adapter for the static IL2CPP parser | `tests/test_native_source_frozen_parity.py`, `tests/test_native_il2cpp_static_probe.py` |
| End-to-end reproducibility chain (denominator -> feature matrix -> AP-11 manifest, byte-identical per fixed run-id) | `tests/test_native_repro_chain.py` |

Gate action weights remain 0: they are completeness/proof features, not
record actions. The AP-11 campaign (6,011 expected actions, 0 confirmed
real-game effect so far) is a separate end goal and is excluded from the
100% feature metric.

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
- **AP-11**: 0 of 6,011 expected actions confirmed with observed
  real-game effect.
- Broad automatic table forms, remote speed control and managed
  invocation remain in development (see
  [`native-runtime.md`](native-runtime.md)).

Fixture tests and a green build never establish game compatibility.
After new Windows or Deck tests, record the observed build (versions,
hashes, test setup, result) here before raising any status.
