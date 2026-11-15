# CT2Trainer Native verification

Status: October 21, 2026 (0.16.1; release build `native-20261021T161241Z-b0566a25`, cut from `main` @ `d1c61f2`).

This document records the **current** verification state of the
independent CT2Trainer Native edition: what is proven, how it is
reproduced, and what remains open. Per-run evidence lives in the local
build run folders (`build/runs/native-<UTC-timestamp>-<id>/`) and is not
committed.

The feature matrix covers 42/42 in-scope features over the 30-table synthetic corpus; that result does not establish support for the full real reference corpus or real-game behavior. The local-only full-reference static catalog (RT-1 rebaseline 2026-10-21: frozen 151-path manifest committed, catalog re-run on the 0.16 source identical per table) still has 2,698 of 117,624 plan entries blocked. AP-11 has 0 confirmed real-game actions, and runtime acceptance remains `runtime_unverified: true`.

## 1. Current baseline

| Item | Value |
| --- | --- |
| Release version | `0.9.0-rc2` released; `0.16.1` in the root `VERSION` file, build `native-20261021T161241Z-b0566a25` cut from `main` @ `d1c61f2` (2026-10-21); previous 0.16 runs `native-20261021T141051Z-17d53c1d` (superseded 0.16 re-cut 3, in-build 3405/25, evidence unrecorded), `native-20261021T123801Z-8c5c4e1e` (superseded field-fix re-cut 2, user-tested, field finding: SC2 table-load warnings), `native-20261020T150115Z-c426fb92` (superseded field-fix re-cut, user-tested) and `native-20261020T103508Z-0e3f9d90` (superseded, pre field-fix, user-tested); previous `0.15` build `native-20261018T055505Z-39f20180` cut from `main` @ `ed0b97b` (2026-10-18); previous `0.14` build `native-20261017T115850Z-1ebb48b7` cut from `main` @ `fca6b06` (2026-10-17); previous `0.13` build `native-20261016T190005Z-b3139b30` cut from `main` @ `d57e62c` (2026-10-16); previous 0.13 run `native-20261016T181516Z-b8ae88de` (superseded, pre module-snapshot fallback); previous `0.12` build `native-20261016T163910Z-d047f2d2` cut from `main` @ `ba1d3e4` (2026-10-16); previous `0.11` build `native-20261012T092729Z-2d8aaf12` cut from `main` @ `9a76eb8` (2026-10-12) |
| Build entry point | `scripts/Build-Native.ps1` (fully offline, no network) |
| Full native suite | **3412 OK / 25 expected skips, 0 failures** (full local dev suite on `main` after the 0.16.1 SC2 table-load warning fix — table-version reference 45 → 46 + accurate `{$LUA}`/external-action warnings — verified 2026-10-21 at the canonical path with CT2TRAINER_NASM set; previously 3405 on `main` after the 0.16 field-fix round 2 — state-lock self-repair and reliable restart — verified 2026-10-21 at the canonical path with CT2TRAINER_NASM set; previously 3398 on `main` after the 0.16 field-fix cycle — WP-58 UI startup crash fix + Sinking City 2 activation-chain runtime evidence — verified 2026-10-20 at the canonical path with CT2TRAINER_NASM set; previously 3393 on `main` after the W4 B4 merges and the case-28/29/30 pins, verified 2026-10-20 at the canonical path; previously 3233 on `main` after the W4 cycle merge and the case-26/27/31 pins, verified 2026-10-19 at the canonical path; previously 3057 on `native-0.15` after the W3 batch 4 merge (WP-37) and the case-24 pin, verified 2026-10-18 at the canonical path, and the in-build suite of the 0.15 cut `ed0b97b`; previously 3046 after the W3 batch 3 merge (WP-41) and the case-22 pin; previously 3001 after the W3 batch 1 + batch 2 merges (WP-39/40/38) and the case-23 + case-21 pins; previously 2943 after the 0.15 prefix-cut field fix `d15268a`; previously 2932 on `main` at the 0.14 cut `fca6b06`, verified 2026-10-17 at the canonical path; previously 2927 on `main` at the 0.13 cut `d57e62c`, verified 2026-10-16; previously 2925 after the debug-logging feature; previously 2910 after the W2-C + W2-B merges and the case-15 part 2 + case-18 pins; previously 2698 after the WP-17 merge `557b2ac`, verified 2026-10-11; previously 2688 after the WP-15 merge `d3316aa`; previously 2679 after the WP-16 merge `38a830d`; previously 2671 on `native-0.9-staged` after the WP-14 gate-test merge `54b172e`); in-build suite 3412/25 passed (build `native-20261021T161241Z-b0566a25`); previously 3405/25 passed (build `native-20261021T141051Z-17d53c1d`, superseded 0.16 re-cut 3); previously 3405/25 passed (build `native-20261021T123801Z-8c5c4e1e`, superseded by 0.16.1); previously 3398/25 passed (build `native-20261020T150115Z-c426fb92`, superseded by the field-fix re-cut 2); previously 3393/25 passed (build `native-20261020T103508Z-0e3f9d90`, superseded by the field-fix re-cut); previously 3057/25 passed (build `native-20261018T055505Z-39f20180`); previously 2932/25 (build `native-20261017T115850Z-1ebb48b7`); previously 2927/25 (build `native-20261016T190005Z-b3139b30`); previously 2925/25 (superseded 0.13 build `native-20261016T181516Z-b8ae88de`); previously 2910/25 (build `native-20261016T163910Z-d047f2d2`); previously 2710/25 (build `native-20261012T092729Z-2d8aaf12`); previously 2698/25 (build `native-20261011T182033Z-f3317337`); previously 2671/25 (build `native-20261011T121914Z-bfc5fc11`) |
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

Verified direct check (2026-11-15, 0.51, repo `main` @ `9e5e906` on
Windows NT 10.0.26300.0 x64, MSVC `cl` 19.44.35229 BuildTools 2022):
preflight run `20261115T035818Z-ed5ba8bd` passed (`FixtureTarget.exe`
sha256 `b6a5c45ced721d345790a45d359747dfb7e69d28bea0dd6d2ea767e1e0d49086`,
PE `0x8664`, single marker, baseline `value=1234` / `pause=0`, ticks
0 -> 3); plan + trainer generated with the in-build venv CLI from the
0.51 template (`FixtureTrainer.exe` sha256
`38afb9790d3fb0f74bfb87b03707cda81d69187927207ae5e0834c5e0dd533bc`);
the frozen generated trainer ran the owned fixture gate
(`--fixture-target` / `--fixture-report`, exit 0) against a live
`FixtureTarget.exe` it spawned itself - report
`ct2trainer-fixture/v1` `passed`, `frozen_runtime: true`,
`ce_runtime_used: false`, 14/14 observations (attach + AOB, value
4321, Lua record write 5432, Lua worker, memscan + foundlist,
keyboard/controller API, NASM/iced encoding, freeze, pause patch,
concurrent-trainer blocked, resume, saved-switch persistence across
target restart, trainer restart, close restore + lock release).
Evidence folders under the git-ignored `build\windows-fixture\`
(preflight + direct-check sub-folders; full record in
`tests/windows/fixture_target/README.md`). Real-game, clean-machine
and Deck / Proton / touch acceptance remain open.

Verified owned process/nth scan gate (2026-11-15, source runtime,
repo `main` @ `a017d5e` + the owned luacall binding lane on Windows
NT 10.0.26300.0 x64, MSVC `cl` 19.44.35229 BuildTools 2022): the
pre-0.51 repin build was cleaned, so the fixture was rebuilt from the
unchanged source (`scan_target.c` sha256
`4c939ab3c42aeea7eb2211253af8f7bbb374646afd12d744d06685bb7b72808f`,
single git commit `b6c48cc`; CT unchanged at sha256
`440a5bf3fdaaae5e2756eed16f8728efd3c65c7c40084e2a0685f2e2c83366db`)
into run `native-scan-fixture-20261115T043627Z-cfea6da9`
(`verification.json` passed, `ce_inputs: []`; x64 target sha256
`e54b12801564aed37ad9ee3ed3283459e53f9f69ee8042af73730fc0784c5315`,
x86 target sha256
`d66756a12c741caf163823a26643bce5c0a0369c8b689fc00f0a3f52fa8a626e`;
`scan_probe.py` re-pinned). The first run failed the open luacall
gate (`no luacall binding factory`, fail-closed); the new owned
luacall binding
(`src/ct2trainer/native/luacall_binding.py`, wired at the trainer /
Master / scan-probe construction sites, engine default stays
fail-closed, generic luaCall names stay refused by exact name -
AP-11) closed it. Re-run through the source-runtime launcher (0.51
in-build venv python sha256
`5fc3c5244b5eef01a82fbefd1932d1382b79c72fe6e64ffe8df1e3ce3643f02f`,
`--plan` / `--scan-fixture-target` / `--scan-fixture-report`, exit 0):
both x64 and x86 reports `ct2trainer-owned-scan/v1` status `passed`,
`frozen_runtime: false`, `ce_inputs: []`, `owned_markers_absent:
true`, 8/8 checks each (exact-arch target + patterns, compact
process scan + publication + readback, nth source adapter confirmed
+ journaled, add-first does not rebind disable, fresh reactivation
rescans, target restart reapplies wishes, controller restart
restores, final off + cleanup; terminal receipts in valid terminal
states). Plans under
`build\windows-fixture\scan-check-20261115T044000Z-scan\`
(x64 plan sha256
`1a84220daa1d98f62668ea1c7761e703e0229de2ea19b1952df9b11fe4b086e5`,
x86 plan sha256
`fa1939cd1213f3471cb1f6fcca97644c048b3f1c23d8a503adbdc6eb9b09554a`).
Full record in `tests/windows/scan_fixture/README.md`. The frozen
scan gate (`frozen_runtime: true`, the generated
`ScanTrainer.exe`) was re-run at the 0.52 release cut (run
`native-20261115T070952Z-14405931`, cut from `main` @ `26e6ebc`):
the two frozen scan trainers were regenerated from the gate-passed
plans with the 0.52 template stub (sha256
`23e8fed027b0e50f5bc1f81f7b7b626b6df951f5de8ba2a0e7c43fefbbf2d4a9`
- the pre-cut trainers carried the pre-binding 0.51 template) and
both reports `ct2trainer-owned-scan/v1` passed - `frozen_runtime:
true`, `ce_inputs: []`, `owned_markers_absent: true`, 8/8 checks
each, plan identity identical to the source runtime (frozen x64
trainer sha256
`283e50759750774bcd3c3b8c04020a58f87ac3ff94e4f74f233a28305d7745f5`,
frozen x86 trainer sha256
`8ebc01935a3bb70bfac6439c30c3f3ec8d540368426a8e79c189009a4703cb12`);
see "Verified frozen scan gate (2026-11-15, 0.52 build cut)" in
`tests/windows/scan_fixture/README.md`. Real-game, clean-machine
and Deck / Proton / touch acceptance remain open.

Verified owned String gate (2026-11-15, source runtime, repo
`main` @ `3519dcd` post-0.52 on Windows NT 10.0.26300.0 x64, MSVC
`cl` 19.44.35229 BuildTools 2022): the 2026-10-07 repin build was
cleaned, so the fixture was rebuilt from the unchanged source
(`string_target.c` sha256
`9c69ea3549387956551e96d501a5184765d59df36cae2cc32936ca81b0877652`,
single git commit) into run
`native-string-fixture-20261115T085726Z-b2cade29`
(`verification.json` passed). The fresh builds are
byte-nondeterministic (second independent rebuild differed in hash
for both architectures) but layout-stable, so `string_probe.py`
`TARGET_SHA256` was re-pinned to the fresh EXEs (x64
`46e3f47e60b1ca77fcd16cd3b0d5a57ba3a131029c5b107cb91cab297a23e852`,
x86
`3c22495e86ace0999b64f10d35e2c276d753d62667daa2347077cc76009f5ab7`);
the fresh x64 image keeps the 2026-10-07 layout exactly (x64 CT
unchanged, freshly compiled x64 plan fingerprint byte-identical to
the pinned
`fc1ff36bcfa1bba926cf792a0e62ec619aaaa21866f424a19cbe4d2bb07c59f8`
- compiler determinism confirmed), while the fresh x86 image places
its static data block a uniform 0x40 lower (ascii `0x1DE40` ->
`0x1DE00`, spacing unchanged), so the x86 CT addresses + probe
`LAYOUT['x86']` were re-pinned together (new x86 CT sha256
`95e30b8ef100e16414b43d916e1d70ef025131433fd8847fea50f0dc170ff984`,
plan fingerprint
`e49036db5a725a08ebaa3e499a74e9dde4913b2d5265a9cf070912f5312c6640`;
the `TARGET_SHA256` hash gate still bounds every acceptance).
Re-run through the source-runtime launcher (0.52 in-build venv
python, `PYTHONPATH=src`, `--plan` / `--string-fixture-target` /
`--string-fixture-report`, exit 0): both the x64 and x86 reports
`ct2trainer-owned-string/v1` status `passed`, `frozen_runtime:
false`, `ce_inputs: []`, `owned_markers_absent: true`, 14/14 checks
each (child identity / regions / RVAs / sentinels, real
ascii-utf16-surrogate-and-fixed reads, invalid-literal refusals,
precise prefix writes with tail + guard preservation, fixed
literal exact units, wrong-protection refusals without byte or
protection change, freeze tail/last-byte behavior, fresh held-freeze
prefix repair, frozen prefix-overlap refusal, apply-updated freeze
intent, live controller restart drops freeze, target
restart-attach fresh, final close + owned exit). Plans + reports
under `build\windows-fixture\string-check-20261115T095000Z-string\`.
Full record in `tests/windows/string_fixture/README.md`. The frozen
String gate is re-run at the next release cut; real-game,
clean-machine and Deck / Proton / touch acceptance remain open.

Verified owned x86 debug-hook gate (2026-11-15, source runtime, repo
`main` @ `0367d7b` post-0.52 on Windows NT 10.0.26300.0 x64, MSVC
`cl` 19.44.35229 BuildTools 2022): the 2026-10-07 repin build was
cleaned, so the fixture was rebuilt from the unchanged source
(`hook_stress_target.c` sha256
`967e035a7aef7b213726d4fd80ffb03d0d214224aabeeebcbda1a27468cc05f1`,
single git commit) through the directory's new first-party recipe
`tests/windows/debug_hook_fixture/Invoke-DebugHookFixtureBuild.ps1`
into run `native-debughook-fixture-20261115T104212Z-c84316ed`
(`verification.json` passed). The re-pin is hash-only - the gate CT
and AA program source are unchanged (the entry is an `aobscanmodule`
AOB, no fixed RVAs), so only `x86_probe.py` `TARGET_SHA256` moved to
the fresh x86 EXE
(`12f8304ef6857e08a67f5204dbdeff0456d6be3a4861561def8fe68d137c94cb`);
a read-only pre-flight spawn proved the fresh child's metadata line
contract and the exact 12-byte entry pattern before the re-pin, and
the hash gate still bounds every acceptance. Re-run through the
source-runtime launcher (dev venv python, `PYTHONPATH=src`, `--plan`
/ `--x86-fixture-target` / `--x86-fixture-report`, exit 0): report
`ct2trainer-owned-x86/v1` status `passed`, `frozen_runtime: false`,
`ce_inputs: []`, 6/6 checks (canonical x64 rebinding plan refused
before any session or effect; 4->103 confirmed pushad/pushfd hook
saved as ON; x86 Lua pointer width + remote export + coordinated
literal write with independent readback; exact disable + retired
executable retention; target exit finalizes receipts preserving
saved ON; saved ON restores on a fresh identity with final disable +
close - the debugger-coordinated hook carries 8 held thread-context
observations). Plans + reports under
`build\windows-fixture\x86-check-20261115T105517Z\`. Full record in
`tests/windows/debug_hook_fixture/README.md`. The frozen x86 gate is
re-run at the next release cut; real-game, clean-machine and Deck /
Proton / touch acceptance remain open.

Verified owned hook gate + owned Lua-record gate (2026-11-15, source
runtime, repo `main` @ `cb04cc8` post-0.52 on Windows NT
10.0.26300.0 x64, MSVC `cl` 19.44.35229 BuildTools 2022): the
2026-10-02 pin build of the shared x64-only fixture
(`NativeHookFixture.exe`) was cleaned, so it was rebuilt from the
unchanged source (`hook_target.c` sha256
`ec84fbe293257a847e6eb14d5a56ca72dfd3acc466a4e75b979289c3795d0b7d`,
single git commit) through the directory's new first-party recipe
`tests/windows/hook_fixture/Invoke-HookFixtureBuild.ps1` into run
`native-hook-fixture-20261115T112832Z-137263bc`
(`verification.json` passed, EXE sha256
`37c02a22bff3c1b46033e7ff8ef37338fb3f8c8fa70f8b5e6e3bb0fab1567421`,
PE machine 0x8664). The re-pin is hash-only - both gate CTs and all
three Lua-record source profiles are unchanged (the entry is an
`aobscanmodule` AOB, no fixed RVAs), so only `lua_record_probe.py`
`TARGET_SHA256` moved (`hook_probe.py` pins no target hash by design);
a read-only pre-flight spawn proved the fresh child's bounded
metadata line contract, the unique 8-byte entry pattern (RVA `0x26000`
in `.tfnhook`), the packed `fixture_result` / `fixture_calls` export
pair and one common implied image base before the re-pin, and the
hash gate still bounds every acceptance. Re-run through the
source-runtime launcher (dev venv python, `PYTHONPATH=src`, `--plan`
/ `--hook-fixture-target` / `--hook-fixture-report` then `--plan` /
`--lua-fixture-target` / `--lua-fixture-report`, both exit 0): hook
report `ct2trainer-frozen-hook/v1` status `passed`,
`frozen_runtime: false`, `ce_inputs: []`, 7/7 checks (remote-export
value address + original effect; iced-debugger-confirmed hook saved;
upstream-Lua53 record write + independent readback; exact disable +
saved wish cleared; retired cave readable before target exit; target
exit finalizes retained code; controller state ownership released) and
Lua report `ct2trainer-frozen-lua-record/v1` status `passed`,
`frozen_runtime: false`, `ce_inputs: []`, 4/4 checks (compiler-to-
automatic-Lua receipts + owned write + cooperative worker; scoped
provider + dependency refusal before cancellation; disable with
inverse raw undo + callback cancellation; fresh activation, target
exit finalization and confirmed saved-state restart). Plans + reports
under `build\windows-fixture\hook-check-20261115T135250Z\`. Full
record in `tests/windows/hook_fixture/README.md`. Both frozen gates
re-run at the next release cut; real-game, clean-machine and Deck /
Proton / touch acceptance remain open.

Verified owned global gate, both architectures (2026-11-15, source
runtime, repo `main` @ `992326c` post-0.52 on Windows NT 10.0.26300.0
x64, MSVC `cl` 19.44.35229 BuildTools 2022): the 2026-10-07 pin build
of both targets had been cleaned, so `NativeGlobalFixture.exe` was
rebuilt for x64 + x86 from the unchanged source (`global_target.c`
sha256 `c44cbe404954678ca753f81b17f6d9c1c17d16558755a79bcb982a983ebec6aa`)
through the directory's committed recipe
`tests/windows/global_fixture/Invoke-GlobalFixtureBuild.ps1` (marker
+ probe prologue occurrence == 1 each) into run
`native-global-fixture-20261115T144546Z-f569` (`build.json` schema
`ct2trainer-owned-global-build/v1` status `passed`, x64 EXE sha256
`cd74ef9285309e95251eea5df3181c5134cf4c6487b0965629114a96a188387e`,
x86 EXE sha256
`b69cc968997d1ede53176aaa6c8cdbfebe6deee7838b7f064270f6dc8530bc56`).
The re-pin is hash-only - both pinned CTs and the fixture source are
unchanged, so only `global_probe.py` `TARGET_SHA256` moved for both
architectures, and the canonical plan fingerprints (`PLAN_SHA256`)
still hold byte-for-byte against the compiled plans (no compiler
drift); a read-only pre-flight spawn proved both fresh children's
bounded metadata line contract, the marker/proprobe sentinels read
back byte-exact through independent OpenProcess / ReadProcessMemory,
one probe status reply (`sequence=1`, `probe_value=0x5A5B5C5D`) and
the quit exit 0 before the re-pin, and the hash gate still bounds
every acceptance. Re-run through the source-runtime controller
(`global_probe.run_probe` per architecture, dev venv python,
`PYTHONPATH=src`, fresh `'x'` reports): both reports
`ct2trainer-owned-global/v1` status `passed`,
`source_runtime: true`, `frozen_runtime: false`,
`ce_implementation_inputs: []`, `owned_markers_absent: true`, 14/14
checks per architecture (identity/module metadata; baseline probe;
near-marker RW allocation + 333 init; patched-entry roundtrip;
value-record write through the symbol; disable retention + hidden
symbol; second-controller refusal; target-exit pool retirement;
normal close cleanup; stale-journal fence; fresh-identity re-spawn;
fresh-session roundtrip; final close) plus the recorded live-close
fence refusal with entry restored, storage retained and all markers
preserved. Plans + reports under
`build\windows-fixture\global-check-20261115T145222Z\`. Full record
in `tests/windows/global_fixture/README.md`. The frozen re-run
happens at the next release cut; real-game, clean-machine and Deck /
Proton / touch acceptance remain open.

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
