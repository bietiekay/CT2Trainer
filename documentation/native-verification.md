# CT2Trainer Native verification

Status: November 23, 2026 (0.52.1; release build `native-20261115T181026Z-00f5dfe8`, cut from `main` @ `dc138e0`, 2026-11-15).

This document records the **current** verification state of the
independent CT2Trainer Native edition: what is proven, how it is
reproduced, and what remains open. Per-run evidence lives in the local
build run folders (`build/runs/native-<UTC-timestamp>-<id>/`) and is not
committed.

The feature matrix covers 42/42 in-scope features over the 30-table synthetic corpus; that result does not establish support for the full real reference corpus or real-game behavior. The local-only full-reference static catalog (RT-1 rebaseline 2026-10-21: frozen 151-path manifest committed) currently has 193 of 117,809 plan entries blocked (baseline `blocked-catalog-luacall-binding`; all 151/151 table paths load, every remaining block covered by a documented gate or a 0.44-0.51 ratification lane). AP-11 has 0 confirmed real-game actions, and runtime acceptance remains `runtime_unverified: true`.

## 1. Current baseline

| Item | Value |
| --- | --- |
| Release version | `0.52.1` in the root `VERSION` file, build `native-20261115T181026Z-00f5dfe8` cut from `main` @ `dc138e0` (2026-11-15); previous `0.52` build `native-20261115T070952Z-14405931` (2026-11-15); previous `0.51` build `native-20261115T023110Z-4ed2835e` (2026-11-15); previous `0.50` build `native-20261114T223759Z-086989d6` (2026-11-14); previous `0.49` build `native-20261114T184922Z-4b721a9e` (2026-11-14); previous `0.48` build `native-20261114T133842Z-8ee6999f` (2026-11-14); previous `0.47` build `native-20261114T011046Z-ee5cecee` (2026-11-14); previous `0.46` build `native-20261113T185658Z-e543af1a` (2026-11-13); previous `0.45` build `native-20261113T144426Z-572d5b30` (2026-11-13); previous `0.44` build `native-20261112T233337Z-1dc678c6` (2026-11-13); previous `0.43` build `native-20261111T184600Z-3bf9d8aa` (2026-11-11); previous `0.42` build `native-20261111T044023Z-04112d15` (2026-11-11); previous `0.41` build `native-20261110T210856Z-5811040c` (2026-11-10); previous `0.40` build `native-20261110T093203Z-82c49872` (2026-11-10); previous `0.39` build `native-20261110T051241Z-57bf7d47` (2026-11-10); previous `0.38` build `native-20261109T211151Z-03e89050` (2026-11-09); previous `0.37` build `native-20261109T154005Z-4ad8e339` (2026-11-09); previous `0.36` build `native-20261109T114726Z-15c3d9ab` (2026-11-09); previous `0.35` build `native-20261109T054146Z-c5f18494` (2026-11-09); previous `0.34` build `native-20261109T024143Z-a5457911` (2026-11-09); previous `0.33` build `native-20261108T200230Z-b0167049` (2026-11-08); previous `0.32` build `native-20261108T100731Z-a1d311e5` (2026-11-08); previous `0.31` build `native-20261105T080853Z-2e7f50a5` (2026-11-05); previous `0.30` build `native-20261104T131114Z-11522f68` (2026-11-04); previous `0.29` build `native-20261104T094808Z-50af0517` (2026-11-04); previous `0.28` build `native-20261103T161621Z-ea8fde2f` (2026-11-03); previous `0.27` build `native-20261103T145543Z-b29b3688` (2026-11-03); previous `0.26` build `native-20261103T112811Z-59a6b3d5` (2026-11-03); previous `0.25` build `native-20261103T062439Z-f4c16be9` (2026-11-03); previous `0.24` build `native-20261102T102029Z-fe358e35` (2026-11-02); previous `0.23` build `native-20261101T145310Z-a160bae4` (2026-11-01); previous `0.22` build `native-20261101T075049Z-f32c112d` (2026-11-01); previous `0.21` build `native-20261031T211046Z-14707e12` (2026-10-31); previous `0.20.1` build `native-20261031T104114Z-d64ae4c2` (2026-10-31); previous `0.20` build `native-20261030T184820Z-b9d6dc07` (2026-10-30); previous `0.19` build `native-20261030T121918Z-c72dbb38` (2026-10-30); previous `0.18` build `native-20261028T131208Z-55922918` (2026-10-28); previous `0.17` build `native-20261027T094839Z-ec6c6f55` (2026-10-27); previous `0.16.4` build `native-20261024T003853Z-a8cf04fc` (2026-10-24); previous `0.16.3` build `native-20261023T065015Z-afbc3eba` (2026-10-23); previous `0.16.2` build `native-20261022T160328Z-0423fb21` (2026-10-22); previous `0.16.1` build `native-20261021T161241Z-b0566a25` (2026-10-21); previous `0.16` builds `native-20261020T150115Z-c426fb92` / `native-20261020T103508Z-0e3f9d90` (2026-10-20); previous `0.15` build `native-20261018T055505Z-39f20180` (2026-10-18); previous `0.14` build `native-20261017T115850Z-1ebb48b7` (2026-10-17); previous `0.13` build `native-20261016T190005Z-b3139b30` (2026-10-16); previous `0.12` build `native-20261016T163910Z-d047f2d2` (2026-10-16); previous `0.11` build `native-20261012T092729Z-2d8aaf12` (2026-10-12); the full per-build history (superseded field-fix re-cuts, user-tested findings) is in the progress ledger |
| Build entry point | `scripts/Build-Native.ps1` (fully offline, no network) |
| Full native suite | **5,232 OK / 36 expected skips, 0 failures** (full main suite on `main` @ `9a16d86`, verified 2026-11-21 at the canonical path with CT2TRAINER_NASM set); in-build suite 5,203/36 passed (build `native-20261115T181026Z-00f5dfe8`, the 0.52.1 cut); previously 5,197/36 in-build (build `native-20261115T070952Z-14405931`, 0.52), 5,184/36 (0.51), 5,171/36 (0.50), 5,155/36 (0.49), 5,127/36 (0.48), 5,108/36 (0.47), 5,071/36 (0.46), 5,062/36 (0.45), 5,049/36 (0.44), 5,011/36 (0.43), 4,926/35 (0.42), 4,917/35 (0.41), 4,879/35 (0.40), 4,833/30 (0.39), 4,760/30 (0.38), 4,733/30 (0.37), 4,665/30 (0.36), 4,610/30 (0.35), 4,543/30 (0.34), 4,499/30 (0.33), 4,483/30 (0.32), 4,414/30 (0.31), 4,386/30 (0.30), 4,370/30 (0.29), 4,357/30 (0.28), 4,342/30 (0.27), 4,320/30 (0.26), 4,259/30 (0.25), 4,193/30 (0.24), 4,176/30 (0.23), 4,061/30 (0.22), 4,044/30 (0.21), 3,854/26 (0.20.1), 3,850/26 (0.19), 3,767/25 (0.18), 3,692/25 (0.17), 3,412/25 (0.16.1, the last 25-skip baseline); the older per-build chain (2,671/25 at the 0.10 offline build `native-20261011T121914Z-bfc5fc11` and below) is in the progress ledger |
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
Full record in `tests/windows/string_fixture/README.md`. The
String lane was re-pinned a second time before the 0.52.1 cut
(the pin build had been cleaned; rebuild
`native-string-fixture-20261115T174324Z-45f4` from the unchanged
source, `TARGET_SHA256` x64
`7b815ff5148180b434a7ebe543411b54e4d5ce90399ed83e4bf8ecc5f77eb0fd`
/ x86
`7876bf70a8feab52a5774802708d82f1eab36f435231ba3045c59a7b7a7f0668`,
both CTs + plan fingerprints unchanged, both gates re-verified
14/14 in the source runtime). The frozen String gates
(`frozen_runtime: true`, the generated string trainers) were
re-run at the 0.52.1 release cut (run
`native-20261115T181026Z-00f5dfe8`, 0.52.1 template stub sha256
`df004f1afeea2d73fffe1747bb24e8139318311ac59893ea65759a9bf365e040`):
frozen x64 trainer sha256
`7943372c45f2521b93f65ecbe952ef387efa3612e4907b51fa899291e4120bcc`,
frozen x86 trainer sha256
`e225c9adc45997a820ef0871341a087d1a0c5b885c645c4954e6a7f7e5d238b5`;
both reports `ct2trainer-owned-string/v1` status `passed`,
`frozen_runtime: true`, 14/14 checks each; see "Verified frozen
String gate (2026-11-15, 0.52.1 build cut)" in
`tests/windows/string_fixture/README.md` and the 0.52.1 release
build record in `documentation/native-progress.md`. Real-game,
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
`tests/windows/debug_hook_fixture/README.md`. The frozen x86 gate
(`frozen_runtime: true`, the generated x86 trainer) was re-run at
the 0.52.1 release cut (run
`native-20261115T181026Z-00f5dfe8`, 0.52.1 template stub sha256
`df004f1afeea2d73fffe1747bb24e8139318311ac59893ea65759a9bf365e040`):
frozen trainer sha256
`425e81bf49743a09c91df76f5283dda60c89cb844d59a918c0abaf4231bb1813`,
plan identity identical to the source runtime (canonical plan
sha256
`81bbc942c9b626af46c924a514f0af91e9da7ab914aba0cf91e18a25f3de7f0d`);
report `ct2trainer-owned-x86/v1` status `passed`,
`frozen_runtime: true`, 6/6 checks; see "Verified frozen x86 gate
(2026-11-15, 0.52.1 build cut)" in
`tests/windows/debug_hook_fixture/README.md` and the 0.52.1 release
build record in `documentation/native-progress.md`. Real-game,
clean-machine and Deck / Proton / touch acceptance remain open.

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
(`frozen_runtime: true`, the generated trainers) were re-run at the
0.52.1 release cut (run `native-20261115T181026Z-00f5dfe8`, 0.52.1
template stub sha256
`df004f1afeea2d73fffe1747bb24e8139318311ac59893ea65759a9bf365e040`):
frozen hook trainer sha256
`272f3c755970baf1259e75f98e6ee16c5a16eb6e613b4f4d6692fc16cf96e944`,
frozen Lua-record trainer sha256
`65d2ce70da27281e94b6a9ccbfc2668be2f499922e44437d3351ca8020653c70`,
plan identity identical to the source runtime (canonical plan
sha256 `63b98c5ac105e5969d396bd2b0f629316189802e97515a9751df708db177bfcd`
hook,
`620f96597653151e1a69d235bc9a8ad15505c9e4012146f94c2986d08570433e`
Lua-record); hook report `ct2trainer-frozen-hook/v1` status
`passed`, `frozen_runtime: true`, 7/7 checks; Lua report
`ct2trainer-frozen-lua-record/v1` status `passed`,
`frozen_runtime: true`, 4/4 checks; see "Verified frozen hook +
Lua-record gates (2026-11-15, 0.52.1 build cut)" in
`tests/windows/hook_fixture/README.md` and the 0.52.1 release
build record in `documentation/native-progress.md`. Real-game,
clean-machine and Deck / Proton / touch acceptance remain open.

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
in `tests/windows/global_fixture/README.md`. Both frozen global
gates (`frozen_runtime: true`, the generated trainers) were re-run
at the 0.52.1 release cut (run
`native-20261115T181026Z-00f5dfe8`, 0.52.1 template stub sha256
`df004f1afeea2d73fffe1747bb24e8139318311ac59893ea65759a9bf365e040`):
frozen x64 trainer sha256
`a96d407911a4223a5d93fc4f706e6c0820ac15674f343bda71d019736e31030e`
(plan sha256
`bd89b62363e1800424a66efdf5f31b9459d5cc0ee7e9730a081d9773e8601865`),
frozen x86 trainer sha256
`eef0cea97a3f2666df340a6e80981a2b6a8492c37092007df2c504c5fe09e683`
(plan sha256
`2f443b73f0ab4e9b7a827f433a20fd4d248ec0f67f541b92553735e9f1af191e`);
both reports `ct2trainer-owned-global/v1` status `passed`,
`frozen_runtime: true`, 14/14 checks each; see "Verified frozen
global gate (2026-11-15, 0.52.1 build cut)" in
`tests/windows/global_fixture/README.md` and the 0.52.1 release
build record in `documentation/native-progress.md`. Real-game,
clean-machine and Deck / Proton / touch acceptance remain open.

Verified owned clock gate, both architectures (2026-11-15, source
runtime, repo `main` @ `fc20da5` post-0.52 on Windows NT
10.0.26300.0 x64, MSVC `cl` 19.44.35229 BuildTools 2022): the
owned local clock fixture is production code under
`src/ct2trainer/native/clock/` with no pinned target image, so no
re-pin was needed - the clock EXE gate
(`Invoke-ClockFixture.ps1`, both archs, `/W4 /WX /O2`) produced
run `native-clock-20261115T151926Z-a58a` (`verification.json`
schema `ct2trainer-clock-verification/v1` status `passed`, x64
EXE sha256
`ffc4403f4087abf5d0b054c3f08704cbb8f480ce0efee426ac8064a5529517cd`,
x86 EXE sha256
`8b4db62bf9b56ea1163e85cf54f5d776718d7ec8685e05f9d300e078a3bc1e5a`,
1,146 internal checks + 256 conversion vectors per arch), and the
env-gated oracle tests (`test_native_clock.py` with
`CT2TRAINER_CLOCK_FIXTURE` set per EXE) passed 2/2 per
architecture - the local rate / epoch / lease / fault /
concurrency contract plus the 256-case integer conversion
against the arbitrary-precision reference. The owned local
adapter DLL lane (`Invoke-ClockAdapterFixture.ps1`, production
build without the `-TestPlatformFault` export, `/W4 /WX /O2
/MT`) produced run
`native-clock-adapter-20261115T153125Z-da22` (`verification.json`
schema `ct2trainer-clock-adapter-verification/v2` status
`passed`, 14 host runs - 7 modes per architecture, each loading
only its exact freshly built DLL; x64 DLL sha256
`58ceeb327796a061f79fa8294f5a047bcbf032e1c95997d2adb122fee1d80e7d`,
x86 DLL sha256
`b8174c4af4c89797ebc2670e75075c9f3bb9173cabedbe4765c7e74b09cf18d0`),
plus the optional instrumented
(`-TestPlatformFault`) lane (run
`native-clock-adapter-fault-20261115T160210Z-fcc5`, status
`passed`, `test_only_platform_fault_export: true`, 16 host runs -
the 7 production modes + the instrumented `platform` mode per
architecture, instrumented x64 DLL
`f51fdca389cda20349de9318fec75319d7ad68d196f16d898697757bf995e5ac`
/ instrumented x86 DLL
`1aab919b266c31f2c11f3cf0df1413074356d2185f7a33b872000280000e0914`;
faulted submissions rejected, fault-during-pending produces the
explicit snapshot-less fault ACK, production DLLs carry no
fault-injection export).
Full record in `tests/windows/clock_fixture/README.md`. Hook
admission/relocation, remote control, static / dynamic API
interception and the game / Proton claims remain open, so
`runtime_unverified` stays set.

Verified owned code-patch gate, x64 (2026-11-16) + x86
(2026-11-20), source runtime, repo `main` @ `a4e805d`
post-0.52.1 + the code-patch lane (x64, lane uncommitted at
measurement time) / `main` @ `24ddb71` (x86, lane committed
`bf30313`) on Windows NT 10.0.26300.0 x64, MSVC `cl`
19.44.35229 BuildTools 2022: the 9th Windows function gate
(RT-6 fixture-owned, house pattern per `global_probe.py`). The owned code-patch fixture
(`tests/windows/codepatch_fixture/codepatch_target.c` sha256
`89f1bef4b4f59fbd6653bd9eb1ff6777d321c740bde30d2741f7af56fe7a52e9`)
was built for x64 + x86 through the committed recipe
`Invoke-CodePatchFixtureBuild.ps1` into run
`build\runs\native-codepatch-fixture-20261116T032022Z-bdd3\`
(`build.json` schema `ct2trainer-owned-codepatch-build/v1` status
`passed`, `ce_inputs: []`; x64 EXE sha256
`3f217da553159221216db43c6c8e83481d5da2869edcdf68ca4f66980a9b891f`,
x86 EXE sha256
`288855467feab361c2d27a64a4ff68bb73687923d8e3984003a3c7fe77ae6a85`).
Both pinned CTs (`tests/fixtures/codepatch/`) compile to the pinned
canonical plans (4 supported / selected `code_patch` records, zero
blocks / warnings; x64 plan file sha256
`cef82a71b2cf082a7764f0fd203a47634106468001f3a0eee5496e1dde9360c8`,
plan fingerprint
`6b0ce466529127e1497cc1e47e7ca4d3bbaba198564c1bbb701b4c57155cffa3`;
x86 plan fingerprint
`c67846921cafeedb36387e465efa88fdaa95e80c7526bc485df817b8d6a28061`).
The x64 RVAs were measured from the live target's metadata line;
the x86 RVAs were measured statically by a PE section walk
cross-proven byte-exact against the x64 runtime metadata. Re-run
through the source-runtime launcher (`--plan` /
`--codepatch-fixture-target` / `--codepatch-fixture-report`, exit
0; plan + report under
`build\windows-fixture\codepatch-check-20261116T082357Z\`): the
x64 report `ct2trainer-owned-codepatch/v1` status `passed`,
`source_runtime: true`, `frozen_runtime: false`,
`ce_implementation_inputs: []`, `owned_markers_absent: true`,
14/14 checks (data-page publish / capture / restore, overlap
refusal, target-changed refusal, already-active adoption,
executable-page routing through the verified hook coordinator with
the target's own protocol executing the patched entry, the
restore-mismatch engine block, the blocked engine's action and
second-controller refusals, target-exit finalization of the
blocked session through `close-after-blocked` with both saved
wishes persisted, saved-ON replay of both routes on a fresh
identity, replayed disables with the retained `retired` terminal
receipt, normal close after exit) plus the recorded live-close
fence (a blocked live close on a third owned target refuses with a
`False` return and the exact "code-patch restore mismatch" reason,
touches nothing in the target and preserves every receipt across
the target exit). The x86 source-runtime run **passed 14/14**
on 2026-11-20 (report stamp `20261119T235133Z` UTC; plan +
report under
`build\windows-fixture\codepatch-x86-check-20261119T235133Z\`,
git-ignored): x86 report `ct2trainer-owned-codepatch/v1` status
`passed`, `source_runtime: true`, `frozen_runtime: false`,
`ce_implementation_inputs: []`, `owned_markers_absent: true`,
14/14 checks - the same named checks as the x64 run, against
the pinned x86 target (sha256
`288855467feab361c2d27a64a4ff68bb73687923d8e3984003a3c7fe77ae6a85`,
PE machine 0x14C / pointer width 32, canonical plan
fingerprint `c67846921cafeedb36387e465efa88fdaa95e80c7526bc485df817b8d6a28061`,
plan file sha256
`b5439d46b1febeacb3acc6c2068bca98de60ff00b2ca2943c85551cd2fa412b9`):
the live module metadata confirms the static x86 RVA
measurement byte-exact (marker 0x16190, data_a 0x1D000,
data_b 0x1D008, overlap 0x1D004, probe 0x11A0), the
executable-page enable routes through the verified hook
coordinator and the target's own protocol executes the
patched probe entry 0x46474849, and the dedicated recorded
live-close fence holds (a blocked live close on a third owned
target refuses with a `False` return and the exact "code-patch
restore mismatch" reason, touches nothing in the target and
preserves `state.lock` / `session.json` / `state.json` / the
`enabled`-state executable journal across the target exit).
Machine note: on this VM the x86 target launches only from an
elevated parent - a non-elevated `CreateProcess` fails with
Win32 740 (the name + architecture launch-block heuristic:
any x86 executable with a "patch"-like name was refused
regardless of content, path, parent or caller context, while
x64 binaries with the same names, x86 with clean names and
"dispatch" launch fine); the Smart App Control first-launch
hypothesis is refuted (SAC registry state off / never
enabled, no SAC operations log, no block events, prompt
approval ineffective) and AppLocker / WDAC / SRP are absent or
empty, no MOTW, no elevation manifest, no third-party
AV/EDR. Windows Defender behavior monitoring is the active
enforcer on this VM (registered AV, PUA protection +
realtime + NIS on); a Defender exclusion for the fixture
process + the run paths was added and read back as registered
during the clearance, and the source-runtime run was
performed from an elevated console. The frozen re-run (the
generated trainers, `frozen_runtime: true`) of both
architectures happens at the next release cut, following the
eight-lane precedent. Full record in
`tests/windows/codepatch_fixture/README.md`. Real-game,
clean-machine and Deck / Proton / touch acceptance remain
open, so `runtime_unverified` stays set.

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
