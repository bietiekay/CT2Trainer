# CT2Trainer build guide

Status: October 20, 2026 (0.16; current build `native-20261020T150115Z-c426fb92`).

This guide is self-contained: it covers the requirements, the single build
entry point, the local native test suite, the corpus denominator tool, and
the release content rules of the CT2Trainer Native edition. The Native
build is fully offline and uses no CE implementation inputs or binaries.

## 1. Requirements

- **Windows x64** host (the archived native wheels require Windows x64
  Python 3.12; the build script verifies the runtime before use).
- **git** checkout of this repository (all paths below are relative to the
  repository root).
- **Python 3.12** — the offline build uses the archived portable runtime
  `dependencies/python/python-3.12.14-windows-x64-portable.zip` (hash-checked
  against `dependencies/manifest.json`; expanded into `.tools/python` on
  first use). Local test runs use the development venv at
  `.tools\native-build-env` (Python 3.12, with Lupa 2.8 / iced-x86 1.21.0
  installed offline from `dependencies/native`):

  ```powershell
  & .tools\python\python.exe -m venv .tools\native-build-env
  & .tools\native-build-env\Scripts\python.exe -m pip install --no-index --find-links dependencies\native\lupa --find-links dependencies\native\iced-x86 lupa==2.8 iced-x86==1.21.0
  ```
- **NASM 3.02** (BSD-2-Clause) — the offline build restores the archived
  NASM into each run folder on its own. Local test runs restore it with
  `python tools/native_build.py restore-nasm --output .tools/native-tools`
  (producing `.tools/native-tools/nasm.exe`).
- No network access is required: wheels, PyInstaller and native components
  are installed offline from `dependencies/python/wheels` and
  `dependencies/native/` (lupa==2.8, iced-x86==1.21.0).

## 2. The only build entry point

```bat
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\Build-Native.ps1
```

`scripts\Build-Native.ps1` is the **only** build entry point. Each run:

1. creates a fresh run folder `build/runs/native-<UTC-timestamp>-<id>/`;
2. verifies the archived build inputs (`tools/native_build.py verify-inputs`,
   hash-checked against `dependencies/manifest.json`);
3. creates a fresh venv in the run folder and installs PyInstaller and the
   BSD/MIT native wheels offline;
4. restores the archived NASM into the run folder
   (`tools/native_build.py restore-nasm`);
5. runs the full native test suite (`tools/native_build.py run-tests`,
   producing `suite-tests.log` / `suite-tests.json` with the tested source
   hashes);
6. freezes and audits both EXEs (`tools/native_build.py build`), producing
   `payload-inventory.json` and `build.json`.

Fresh builds produce, in the run folder:

- `CT2Trainer-Converter.exe` and the checked trainer template
  `CT2Trainer-Template.exe` (under `bin/`);
- `CT2Trainer-<version>-source.zip`;
- `CT2Trainer-<version>-windows-portable.zip`.

Each build reports the exact output hashes in the run folder
(`build.json`), e.g. for the current state:

- `CT2Trainer-0.16-source.zip`
- `CT2Trainer-0.16-windows-portable.zip`

**Version:** the release version is the content of the root `VERSION`
file; it is the single version source for Native builds, and
`tools/native_build.py` refuses to run when the file is missing or
empty. Fresh builds are named `CT2Trainer-<version>-source.zip` and
`CT2Trainer-<version>-windows-portable.zip`, where `<version>` is the
current content of `VERSION` (currently `0.16`).

The build report deliberately keeps `runtime_unverified: true` until the
broader acceptance gates pass; a green build is not a game-compatibility
claim.

## 3. Native full test suite (local)

From the repository root in PowerShell, using the development venv:

```powershell
python tools/native_build.py restore-nasm --output .tools/native-tools
$env:PYTHONPATH="src;tests"
$env:PYTHONIOENCODING="utf-8"
$env:CT2TRAINER_NASM=(Resolve-Path .tools/native-tools/nasm.exe).Path
& .tools\native-build-env\Scripts\python.exe -m unittest discover -s tests -p test_native_*.py -q
```

Current in-build baseline: **3398 OK / 25 expected skips / 0 failures** for
`native-20261020T150115Z-c426fb92` (0.16). The 30-table synthetic corpus
measures 6,143 expected actions; its feature matrix covers 42/42 in-scope
features. This does not claim support for the full real reference corpus: 2,698
of 117,624 plan entries remain blocked. AP-11 has 0 confirmed real-game actions,
and the build keeps `runtime_unverified: true`.

Historical baseline: **2671 OK / 25 skips** in the 0.10 offline build
`native-20261011T121914Z-bfc5fc11`.

## 4. Corpus denominator tool

The AP-10 denominator tool is a deterministic, read-only, stdlib-only
static analysis of a `.CT` corpus (no execution of CT Lua/AA content):

```powershell
python tools/corpus_denominator/__main__.py --corpus <dir> --output <dir> --run-id <id>
```

- `--corpus` is the corpus root (treated as strictly read-only; the tool
  refuses to write into it);
- `--output` receives `inventory.json` and `gap-report.json`;
- `--run-id` is the deterministic run stamp (default `repo-reproducible`);
  identical inputs + identical run ID produce byte-identical artifacts.

Committed baselines live under `gap_inventory/`: `inventory.json`,
`gap-report.json`, and `feature-coverage.json` (the feature matrix,
generated by the companion tool `tools/corpus_denominator/feature_matrix.py`
from the same committed artifacts).

## 5. Release content rules

- **Single source of truth:** the explicit allowlist
  `source_files()` in `tools/native_build.py` decides exactly what is
  redistributable. It is shared by the build and by the documentation
  refresh, and covers the native sources (`src/ct2trainer/native/`
  including `clock/` and `target_broker/`), the shared base modules,
  `tools/native_*.py`, `scripts/Build-Native.ps1`, the native tests and
  fixture sources, the byte-pinned MIT/BSD inputs under
  `dependencies/native/` (plus the selected Mono API source inputs), and
  the converter/trainer icons.
- **In-build CE-content scan:** both frozen EXEs are audited by payload
  inventory; forbidden tokens (CE module/payload names, legacy runtime and
  bundle names) in archive entries or module names fail the build, and the
  build report carries `ce_inputs: []`.
- **Release docs allowlist:** `RELEASE_DOC_FILES` in `tools/native_build.py`
  is the exact set of documentation and metadata that ships in the source
  ZIP and that `refresh-source` keeps current: `CHANGELOG.md` (the single
  changelog), `VERSION`, `documentation/native-runtime.md`,
  `documentation/native-verification.md`, `documentation/build.md`,
  `documentation/usage.md`, `documentation/derivation.md`,
  `tests/deck/compatibility-matrix.md`,
  `tests/windows/fixture_target/README.md`, and
  `gap_inventory/feature-coverage.json`. The build **fails** when any of
  these required release docs is absent.
- **No dev-ledger or plan docs in release archives:** development
  ledgers, plan documents and corpus scratch are excluded from
  distributed releases by design.
- **Source ZIP contents:** the allowlisted sources, license notices under
  `licenses/`, the release docs allowlisted above, `.gitattributes`, a
  generated `README.md`, `LICENSE.md`, `requirements-native.txt` and
  `pyproject.toml`. The synthetic corpus (`TableReferences/`) and any CE
  input are **never** included.
- **Portable ZIP contents:** `CT2Trainer-Converter.exe`, the license
  notices, `LICENSE.md`, `CHANGELOG.md`, `payload-inventory.json`, and a
  generated `README.md`.
- Generated trainers copy the checked template and append hash-bound
  declarative plan data; they need no separate Python, NASM, Lua or CE
  installation, and the third-party notices are embedded in them.
