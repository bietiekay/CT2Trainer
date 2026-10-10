# CT2Trainer Native verification

Status: October 10, 2026 (0.9.0-rc2 baseline).

This document records the **current** verification state of the
independent CT2Trainer Native edition: what is proven, how it is
reproduced, and what remains open. Per-run evidence lives in the local
build run folders (`build/runs/native-<UTC-timestamp>-<id>/`) and is not
committed.

## 1. Current baseline

| Item | Value |
| --- | --- |
| Release version | `0.9.0-rc2` (root `VERSION` file) |
| Build entry point | `scripts/Build-Native.ps1` (fully offline, no network) |
| Full native suite | **2617 OK / 25 expected skips** |
| CE inputs in the build | none (`ce_inputs: []` in `build.json`) |
| Runtime acceptance | `runtime_unverified: true`, deliberately kept |
| Corpus denominator | 5,967 expected actions, 1,269 groups (13 pinned case tables) |
| Feature matrix | 39/39 in-scope features; 100% feature-weighted; 7332/7332 action-weighted |

The committed baselines under `gap_inventory/` carry the run stamp
`repo-reproducible` and are reproduced byte-for-byte by the chain in
section 4.

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
| Per-table completeness for all 13 pinned case tables (Forms, table-Lua lifecycle, Custom Types, Assets) | `tests/test_native_table_completeness.py` |
| Source-to-Frozen parity of the 0.9 feature set, plus the binary CLI/GUI adapter for the static IL2CPP parser | `tests/test_native_source_frozen_parity.py`, `tests/test_native_il2cpp_static_probe.py` |
| End-to-end reproducibility chain (denominator -> feature matrix -> AP-11 manifest, byte-identical per fixed run-id) | `tests/test_native_repro_chain.py` |

Gate action weights remain 0: they are completeness/proof features, not
record actions. The AP-11 campaign (5,967 expected actions, 0 confirmed
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
`repo-reproducible`):

```powershell
python tools/corpus_denominator/__main__.py --corpus TableReferences --output gap_inventory --run-id repo-reproducible
python tools/corpus_denominator/feature_matrix.py --output gap_inventory --run-id repo-reproducible
python tools/corpus_denominator/ap11_campaign.py manifest --output gap_inventory --run-id repo-reproducible
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
- **AP-11**: 0 of 5,967 expected actions confirmed with observed
  real-game effect.
- Broad automatic table forms, remote speed control and managed
  invocation remain in development (see
  [`native-runtime.md`](native-runtime.md)).

Fixture tests and a green build never establish game compatibility.
After new Windows or Deck tests, record the observed build (versions,
hashes, test setup, result) here before raising any status.
