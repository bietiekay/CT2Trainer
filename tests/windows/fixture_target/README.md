# Windows x64 test target

`FixtureTarget.exe` is a self-owned console process for the first Windows
function test. It does not access games, other processes, the network, or files.
The C source and `fixture.ct` are reviewable inputs; no Windows runtime execution
of the trainer has been verified in this repository yet.

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
