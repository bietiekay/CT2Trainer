# CT2Trainer

CT2Trainer is an independently authored converter and Windows trainer for
`.CT` (Cheat Engine XML) table files. It reads a table and the exact game
process EXE name, then produces a standalone trainer EXE. The implementation
is a clean-room project: it uses no external trainer source code, binaries or
data — only the public `.CT`/XML format contract and documented behavior are
derived.

## Provenance

This repository — code, tests, tooling, documentation and release
artifacts — is fully AI-generated: developed end-to-end by AI agents
under human direction. AI-authored commits are welcome; the working
contract for agents (boundaries, build rules, lane protocol) is
documented in `AGENTS.md` and
`plans/native-implementation-continuation.md`.

## Screenshots

The converter inspects a `.CT` table, takes the exact target EXE name and
architecture, and lists every record with its include flag and capability:

![CT2Trainer converter UI](documentation/screenshots/ct2trainerui.png)

The generated trainer shows one switch card per record with its current
state, auto-on for the next game launch and navigation; while the target
process is not running, the hooks stay in the waiting state:

![Generated CT2Trainer trainer UI](documentation/screenshots/finishedtrainerui.png)

## Inputs

Every conversion requires exactly two inputs:

1. a **`.CT` table file** (XML format), and
2. the **exact game process EXE name** (basename) the trainer must attach to.

Saved enabled toggles are automatically re-enabled after a successful
re-attach. Only confirmed ON-switches are persisted; a failed enable attempt
stays visibly inactive and is never re-applied as a saved wish. See
[documentation/usage.md](documentation/usage.md) for the full contract.

## Quick start

### Portable ZIP

Run `CT2Trainer-Converter.exe`, open the `.CT` file, enter the exact target
EXE basename, select the records, and build the trainer EXE. No Python,
NASM or other installation is required.

### Source build (Windows x64, fully offline)

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\Build-Native.ps1
```

The build verifies the pinned offline inputs, runs the full test suite, and
produces both `CT2Trainer-<version>-source.zip` and
`CT2Trainer-<version>-windows-portable.zip` plus a build report
(`build.json`) in a fresh `build/runs/` folder. Requirements, the local test
suite, and the release content rules are documented in
[documentation/build.md](documentation/build.md).

## Repository layout

| Path | Purpose |
| --- | --- |
| `src/ct2trainer/native/` | independent converter/trainer implementation |
| `src/ct2trainer/` | shared base modules (table parsing, capabilities, process detection) |
| `tools/` | build helper (`native_build.py`), corpus denominator tooling, icon generator |
| `scripts/Build-Native.ps1` | the single build entry point |
| `tests/` | native test suite, Windows fixture targets, Proton/Steam Deck protocol |
| `TableReferences/` | synthetic clean-room corpus (13 pinned case tables) |
| `gap_inventory/` | committed measurement artifacts (run `repo-reproducible`) |
| `dependencies/` | hash-pinned offline build inputs (Python, PyInstaller, NASM, iced-x86, Lupa, selected Mono API sources) |
| `licenses/` | CT2Trainer MIT grant and third-party notices |
| `documentation/` | build, usage, derivation, runtime, verification and agent-workflow docs |
| `AGENTS.md` | agent handoff: project boundaries, workflow and launch rules (local tooling, not shipped) |
| `plans/` | implementation and continuation plan: work packages, acceptance, open work |

## Verification status

- Full native suite: **2617 OK / 25 expected skips**.
- Feature matrix: **39/39 in-scope features covered** (100% feature-weighted,
  7332/7332 action-weighted) over the pinned corpus of 5,967 expected actions.
- Gates 1–3 (per-table completeness, Source-to-Frozen parity, reproducible
  chain) are closed with tested evidence.
- The AP-11 campaign (observed real-game effect for all 5,967 actions) is a
  separate open end goal and is excluded from the 100% feature metric.
- `runtime_unverified` stays set until real Windows and Steam Deck/Proton
  acceptance runs pass. See
  [documentation/native-verification.md](documentation/native-verification.md).

## License

The independently authored implementation is released under the MIT License
(see [LICENSE.md](LICENSE.md) and `licenses/CT2Trainer-MIT.txt`).
Third-party components ship under their own licenses (MIT/BSD; CPython under
the PSF license; PyInstaller is a GPL-2.0-with-bootloader-exception build
tool whose bootloader is embedded in the generated EXEs). See
[licenses/Native-THIRD-PARTY.txt](licenses/Native-THIRD-PARTY.txt) for the full
notice list.

User-selected CT content is separate input with its author's rights; building
a trainer from a table does not license that table.
