# Windows x64 test target

`FixtureTarget.exe` is a self-owned console process for the first Windows
function test. It does not access games, other processes, the network, or files.
The C source and `fixture.ct` are reviewable inputs. The first Windows function
gate (the owned fixture direct check) was verified 2026-11-15 on the 0.51
build (record below); real-game, clean-machine and Deck / Proton runtime
acceptance remain open.

## Build and run on Windows

For a repeatable Windows-only baseline, open an **x64 Native Tools Command
Prompt for Visual Studio** in the repository root and run:

```bat
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tests\windows\fixture_target\Invoke-FixturePreflight.ps1 -Compiler MSVC
```

Alternatively, in a Windows x64 MinGW-w64 environment use `-Compiler MinGW`.
`Auto` chooses MSVC first, then MinGW-w64. The script creates a unique
`build\windows-fixture\preflight-<run-id>\` folder with `FixtureTarget.exe`,
compiler output, target stdout/stderr, and `preflight.json`. It checks PE x64,
the source/CT hashes, initial `value=1234`/`pause=0`, a single target PID, and
one tick per printed line. It terminates only **its own short-lived baseline
process**. The produced EXE can then be started separately for the
fixture gates and copied alone to the clean VM run. The script does not attach
to any trainer or prove trainer behavior. Keep the printed evidence-folder
path in the run notes (see `documentation/native-verification.md`).

The equivalent manual compiler commands remain useful when diagnosing a
preflight failure. Do not replace a failed local build with an unrelated EXE.

In an **x64 Native Tools Command Prompt for Visual Studio**, from this folder:

```bat
cl /nologo /W4 /O2 /Fe:FixtureTarget.exe fixture_target.c
FixtureTarget.exe
```

Or use a Windows x64 MinGW-w64 compiler:

```bat
x86_64-w64-mingw32-gcc -std=c11 -O2 -Wall -Wextra -o FixtureTarget.exe fixture_target.c
FixtureTarget.exe
```

The process prints its PID and three 32-bit fields once per second. `value`
starts at `1234` and stays unchanged until an external write. `ticks` normally
increases; `pause=1` stops it. Ctrl+C ends the process. Restarting resets all
fields and normally gives a new PID. Keep one instance running when testing
the generator's exact-name attach path.

The CT uses hexadecimal byte offsets from its 16-byte marker: `+10` for
`value`, `+14` for `pause`, and `+18` for `ticks`.

To keep a live target transcript in PowerShell, start the **same hashed EXE**
from the preflight folder in a separate window:

```powershell
& 'C:\path\to\preflight-<run-id>\FixtureTarget.exe' |
    Tee-Object -FilePath 'C:\path\to\fixture-live.log'
```

Replace both example paths. Keep that window open while operating the
trainer, then stop it with Ctrl+C. The PID in its own output must match the
PID shown by the trainer; the target's `value`, `pause`, and `ticks` are the
independent effect evidence. A state label in the trainer alone is insufficient.

## Direct check (Native)

1. Review `fixture.ct`, build and start `FixtureTarget.exe`.
2. Use the Native converter to prepare and inspect the table:
   ```bash
   PYTHONPATH=src python -m ct2trainer.native inspect fixture.ct
   PYTHONPATH=src python -m ct2trainer.native prepare fixture.ct --process FixtureTarget.exe --output build/fixture
   ```
3. Run the generated trainer against the live fixture process. Verify
   `value=4321` after a controlled write, `pause=1` stops `ticks`,
   `pause=0` resumes.

The AA `assert` lines require `pause_ticks` to be `0` when enabling and `1`
when disabling. They prevent an unexpected flag value from being silently
overwritten. The table uses no Lua or injection.

Record the Windows version, x64 compiler/version, binary and CT SHA-256 hashes
(`Get-FileHash` in PowerShell), exact steps, and observed results before
marking any Windows gate complete. A successful local C build or XML parse
does not establish runtime compatibility.

Snapshots around activation, write, restart and failure are captured as
small state files in an ignored local `build/` folder (see
`documentation/native-verification.md` for the native evidence workflow);
review them before sharing evidence. File hashes and process listings are
metadata, not proof that the trainer read or changed the target.

## Verified direct check (2026-11-15, 0.51)

First Windows function gate verified, repo `main` @ `9e5e906`
(0.51 release state, clean tree) on Windows
`Microsoft Windows NT 10.0.26300.0` x64 (PowerShell
5.1.26100.9818), MSVC `cl.exe` 19.44.35229 (BuildTools 2022,
14.44.35207, HostX64\x64), `/W4 /O2 /TC`.

- Preflight run `20261115T035818Z-ed5ba8bd`
  (`build\windows-fixture\preflight-20261115T035818Z-ed5ba8bd\`,
  git-ignored): `FixtureTarget.exe` sha256
  `b6a5c45ced721d345790a45d359747dfb7e69d28bea0dd6d2ea767e1e0d49086`
  (142,336 bytes, PE `0x8664`, single `CT2T-FIX-2026-01` marker),
  `fixture_target.c` sha256
  `1b00c36ea6a2c4de3480c0777d6c13b8a450cd51bb9db8286480a725aab070a8`,
  `fixture.ct` sha256
  `418ba44f2fbfd11c2a8857909a807e519c2a87d1e974e991d1fb268df6a0e92f`;
  baseline PID 3768: `value=1234`, `pause=0`, ticks 0 -> 3 over 4 s
  (one tick per line); `preflight.json` status
  `target-baseline-passed-ce-and-trainer-unverified`.
- Plan + trainer: in-build venv CLI
  (`build\runs\native-20261115T023110Z-4ed2835e\venv\Scripts\python.exe -m
  ct2trainer.native`) - `inspect` (4/4 records supported, process
  `FixtureTarget.exe`), `prepare` (plan JSON), `build` with the 0.51
  `CT2Trainer-Template.exe` -> `FixtureTrainer.exe` sha256
  `38afb9790d3fb0f74bfb87b03707cda81d69187927207ae5e0834c5e0dd533bc`
  (16,901,681 bytes) under
  `build\windows-fixture\direct-check-20261115T040000Z-fixture\`.
- Gate run: the frozen generated trainer was started with
  `--fixture-target <preflight FixtureTarget.exe> --fixture-report
  fixture-report.json` (exit 0); it spawns the target itself. Report
  `fixture-report.json` (schema `ct2trainer-fixture/v1`, status
  `passed`, `frozen_runtime: true`, `ce_runtime_used: false`):
  14/14 observations passed - unique-process attach + AOB (PID 4976),
  independent value readback 4321, upstream Lua 5.3 record write +
  independent readback (5432), owned Lua worker
  createThread/sleep/write/termination, real Lua memscan + foundlist +
  owned module read, read-only keyboard/controller API (no physical
  input claim), pinned BSD NASM + MIT iced machine encoding
  (`89c883c064c3`), freeze confirms current value, pause patch
  (`+14` -> `01000000`, ticks frozen, confirmed persistence),
  concurrent trainer blocked, disable resumes ticks, saved switches
  after target restart (value NOT restored: PID 4976 -> 4996,
  `value=1234`, `pause=1` re-applied from the saved switch),
  trainer restart restores the saved switch, close restores the owned
  patch (`+14` -> `00000000`) and releases the state lock.
  `game_unverified` / `other_pc_unverified` / `proton_unverified` stay
  `true` per gate.

This closes the fixture-owned portion of the Windows runtime evidence
only: real-game, clean-machine and Deck / Proton / touch acceptance
remain open (`runtime_unverified` stays set).
