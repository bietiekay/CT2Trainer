# Owned x86 debug-hook fixture

This subtree is independently authored test material. It contains no CE
input, game table, injection or executable callback beyond the owned
hook the trainer installs under test. It is ignored evidence. Its
first-party source is promoted and included in the Native source-export
allowlist. Compiled target hashes and actual runtime evidence are
recorded separately; a fresh C build does not inherit another binary's
runtime proof.

`hook_stress_target.c` is the concurrent executable-hook target shared
by the owned x86 gate (`NativeDebugHookFixture-x86.exe`) and the x64
stress variant (`NativeDebugHookFixture-x64.exe`, exercised by the
developer tool `tools/native_debug_hook_probe.py`). The entry function
is a const byte array in a dedicated `read, execute`
(`.tfndebug`) section: x86 emits `mov eax,[esp+4]; add eax,1; nop; nop;
ret 4` (bytes `8B 44 24 04 83 C0 01 90 90 C2 04 00`), x64 the
register-passed form. Four caller threads invoke it continuously
(unhooked result `4`), a fifth thread continuously spawns and reaps
transient caller threads; the globals `fixture_result/calls/bad/churn/
stop` are plain `volatile LONG` words the trainer may read and (for
`stop`) write. The first stdout line carries the bounded JSON metadata
contract:

```
{"pid":...,"entry":...,"entry_size":9,"pointer_size":4,
 "result":...,"calls":...,"bad":...,"churn":...,"stop":...}
```

All addresses are the child's own observation. `stop=1` makes the
target join its threads and exit 0; any observed result that is neither
`4` nor `103` sets `bad`, which exits the target with code 5.
`hook_far_target.c` is the far-jump variant used by the developer
stress tool only; it is not part of the gate.

`x86_trainer.ct` (the pinned gate table, 2 records) is a 32-bit Auto
Assembler script that `aobscanmodule`s the 12-byte entry pattern,
allocates next to it, and patches the first 9 bytes with a `jmp` into
a `pushfd/pushad/popad/popfd`-preserving cave that adds 100 to the
returned value (observed `4` -> `103`); the cave also defines the
literal providers `OwnedX86Data` (`1234`) and `OwnedX86Guard`
(`0xDEADBEEF`). Record 2 is the 4-byte value at `OwnedX86Data`.

`Invoke-DebugHookFixtureBuild.ps1 -OutputDirectory <fresh-path>
[-Architectures x64,x86]` creates source snapshots (target source,
gate CT, this build script) and `NativeDebugHookFixture-<arch>.exe`
with MSVC `/W4 /WX /Od /TC` and a nonincremental link, verifying the PE
machine and preserving the compiler command, version and path logs. A
successful build alone does not prove the gate; runtime evidence must
also check exact target identity, refusal of a rebinding x64 plan
before any session, the confirmed 4->103 hook with saved wish, the x86
Lua pointer width + remote export proof, exact disable with retired
executable retention, receipts on target exit, and saved-ON restore on
a fresh identity.

## Verified x86 gate (2026-11-15, source runtime)

First pass of the owned x86 debug-hook gate, repo `main` @ `0367d7b`
(post-0.52; the 0.52 content set is code-identical, so the dev venv
python serves as the source-runtime interpreter with `PYTHONPATH=src`)
on Windows `Microsoft Windows NT 10.0.26300.0` x64 (PowerShell
5.1.26100.9818). The 2026-10-07 repin build
`build/runs/fixture-repin-20261007T115729Z` had been cleaned, so the
fixture was rebuilt from the unchanged source (`hook_stress_target.c`
sha256 `967e035a7aef7b213726d4fd80ffb03d0d214224aabeeebcbda1a27468cc05f1`,
single git commit) with the same MSVC `cl.exe` 19.44.35229
(BuildTools 2022, `/W4 /WX /Od /TC`, nonincremental link) through this
directory's first-party recipe, x86 - fresh run
`build\runs\native-debughook-fixture-20261115T104212Z-c84316ed\`
(git-ignored), `verification.json` (schema
`ct2trainer-owned-debughook-build/v1`) status `passed`.

Unlike the String lane, this re-pin is hash-only: the gate CT is
unchanged (sha256
`6d04714ec6729abf00798d6736eba687c9588c5d4c457c90d9f302f5e442f7c8`,
its entry is an `aobscanmodule` AOB - no fixed RVAs to move) and the
AA program source is unchanged (`x86_probe.py` `SOURCE_SHA256`
`eacbbf87af4c98d7217a3bf0c27b783379a71bc8c0c73a932c08f7dd08553148`
holds), so only `x86_probe.py` `TARGET_SHA256` moved to the fresh x86
EXE (`12f8304ef6857e08a67f5204dbdeff0456d6be3a4861561def8fe68d137c94cb`).
A read-only pre-flight spawn (metadata line contract - pid /
pointer_size 4 / entry_size 9 / integer result/calls/bad/churn/stop -
plus the exact 12-byte entry pattern read back through the child's own
reported entry address, with observed `result=4`, `calls>30`,
`bad=0`) proved the fresh child before the re-pin; the `TARGET_SHA256`
hash gate still bounds every acceptance, so a future rebuild with a
different entry or protocol is refused before any child spawn.

Re-run through the source-runtime launcher (dev venv python,
`PYTHONPATH=src`, `ct2trainer.native.launcher.main` with `--plan` /
`--x86-fixture-target` / `--x86-fixture-report`, exit 0), plan + report
under `build\windows-fixture\x86-check-20261115T105517Z\` (git-ignored;
plan file sha256
`f1eed5ff928ac90a7cc87a652543b9f5b35d7cd98b6950daaa5f2729f73b0926`,
canonical plan sha256
`81bbc942c9b626af46c924a514f0af91e9da7ab914aba0cf91e18a25f3de7f0d`):
report `ct2trainer-owned-x86/v1` status `passed`,
`frozen_runtime: false`, `ce_inputs: []` - 6/6 checks passed:

- canonical_x64_source_plan_refused_before_target_session_or_effect
- explicit_x86_ct_nasm_pushad_pushfd_hook_confirmed_4_to103_and_saved
- x86_lua_pointer_remote_export_and_coordinated_literal_write_independent_readback
- exact_x86_disable_and_retired_executable_retention
- exact_x86_target_exit_finalizes_receipts_and_preserves_saved_on
- saved_x86_on_restores_on_fresh_identity_and_final_disable_closes

The debugger-coordinated hook evidence carries 8 held thread-context
observations; the restarted target obtained a fresh identity.

## Verified frozen x86 gate (2026-11-24, 0.52.2 build cut)

The frozen x86 gate (`frozen_runtime: true`, the generated x86
trainer) was re-run at the 0.52.2 release cut (run
`native-20261124T033652Z-1da5b40e`, cut from `main` @ `cbbd386`): the
frozen trainer regenerated from the gate-passed plan with the 0.52.2
template stub (sha256
`20c17ee135c9bfb388612ade31e1cad5ee032768044f29d4099344017c34ce25`) -
frozen trainer sha256
`4acf53af9a24b72a7d6686a7dc7add2f75475db0af25a8c135188178df5ea927`,
embedded plan sha256
`81bbc942c9b626af46c924a514f0af91e9da7ab914aba0cf91e18a25f3de7f0d` -
plan identity identical to the source runtime - against the rebuilt
x86 target (sha256
`e17e2296c01274bb48c44a41b40f35fba70b4b6bd68c20a138ed320aa888ff5c`,
rebuilt from the unchanged source into
`build\runs\native-debughook-fixture-20261124T031403Z-76b8c44b\`):
ran with `--x86-fixture-target` / `--x86-fixture-report` (exit 0)
against the live x86 target it spawned itself: report
`ct2trainer-owned-x86/v1` status `passed`, `frozen_runtime: true`,
6/6 checks. Evidence under the git-ignored
`build\windows-fixture\frozen-check-20261124T040411Z\`. This record
closes the x86-fixture portion of the Windows runtime evidence only:
real-game, clean-machine and Deck / Proton acceptance remain open
(`runtime_unverified` stays set).
