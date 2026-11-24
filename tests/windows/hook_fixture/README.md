# Owned executable-hook fixture

This subtree is independently authored test material. It contains no CE
input, game table, injection or executable callback beyond the owned
hooks the trainer installs under test. It is ignored evidence. Its
first-party source is promoted and included in the Native source-export
allowlist. Compiled target hashes and actual runtime evidence are
recorded separately; a fresh C build does not inherit another binary's
runtime proof.

`hook_target.c` is the cooperative executable-hook target
(`NativeHookFixture.exe`, x64 only) shared by two owned gates. The
entry function is a const byte array in a dedicated `read, execute`
(`.tfnhook`) section: `mov eax,ecx; add eax,1; nop; nop; ret` (bytes
`8B C1 83 C0 01 90 90 C3`). Two `volatile LONG` globals
(`fixture_result`, `fixture_calls`) are `__declspec(dllexport)`; the
main loop calls the entry in a single cooperative caller thread,
quiescing between calls through the named manual-reset events
`Local\CT2Trainer-Hook-<pid>-{request,ready,resume}` (the trainer's
quiescence protocol holds the caller between the request and resume
events). The first stdout line carries the bounded JSON metadata
contract with exactly the integer keys
`{"pid","entry","result","calls"}`; all addresses are the child's own
observation. Closing the trainer's request event path lets the target
run to its stop-controlled exit.

Two gate tables target it:

- `hook_trainer.ct` (the pinned hook-gate table, 2 records): record 1
  is a 64-bit Auto Assembler script that `aobscanmodule`s the 8-byte
  entry pattern, patches it with a `jmp` into a cave that adds 100 to
  the returned value (observed `4` -> `104`), and restores the original
  bytes on disable; record 2 is the 4-byte value at the module export
  `NativeHookFixture.exe.fixture_result`.
- `lua_trainer.ct` (the pinned Lua-record-gate table, 2 records):
  record 1 is an AA script whose `{$lua}` part auto-assembles a
  scoped `ownedbuf` provider through the automatic-Lua receipts,
  writes `helper()` (17) to it and starts a cooperative worker that
  later writes 19 then 99; the `{$asm}` part hooks the entry to add
  100 only while the Lua-owned `flag` symbol is non-zero, and
  record 2 consumes that provider.

`hook.ct` (1 record, the hook script only) is a developer variant used
by the stress tooling; it is not a probe pin. `coordinator.py`
(`OwnedFixtureCoordinator`) is the developer quiescence helper bound to
a byte-pinned target; the gates carry their own coordination.

`Invoke-HookFixtureBuild.ps1 -OutputDirectory <fresh-path>` creates
source snapshots (target source, both gate CTs, this build script) and
the x64 `NativeHookFixture.exe` with MSVC `/W4 /WX /Od /TC` and a
nonincremental link, verifying the PE machine and preserving the
compiler command, version and path logs. A successful build alone does
not prove the gates; runtime evidence must also check exact target
identity, remote-export resolution, the confirmed hook effects with
independent readback, exact disable with retired-code retention,
target-exit finalization and state ownership release (hook gate), and
the automatic-Lua receipts, provider scoping, cancellation semantics
and saved-state restart (Lua-record gate).

## Verified hook + Lua-record gates (2026-11-15, source runtime)

First pass of both gates against the shared fresh target, repo `main`
@ `cb04cc8` (post-0.52; the 0.52 content set is code-identical, so the
dev venv python serves as the source-runtime interpreter with
`PYTHONPATH=src`) on Windows `Microsoft Windows NT 10.0.26300.0` x64
(PowerShell 5.1.26100.9818). The 2026-10-02 pin build had been
cleaned, so the fixture was rebuilt from the unchanged source
(`hook_target.c` sha256
`ec84fbe293257a847e6eb14d5a56ca72dfd3acc466a4e75b979289c3795d0b7d`,
single git commit) with the same MSVC `cl.exe` 19.44.35229
(BuildTools 2022, `/W4 /WX /Od /TC`, nonincremental link) through this
directory's new first-party recipe, x64 - fresh run
`build\runs\native-hook-fixture-20261115T112832Z-137263bc\`
(git-ignored), `verification.json` (schema
`ct2trainer-owned-hook-build/v1`) status `passed`.

The re-pin is hash-only: both gate CTs are unchanged on disk
(`hook_trainer.ct` sha256
`41f98a015e72244e55e82cf7c2e09c26e87330f6ce800557a7362b409d1eff56`
holds the `hook_probe.py` pin, `lua_trainer.ct` sha256
`6779cb6ce8f7e03cc4aacf7fb18d6677ecb7e2e520e6ff64335f063c4c74654f`
holds the `LUA_CT_SHA256` pin) and all three Lua-record source
profiles (`LUA_SOURCE_SHA256` / `STATIC_SOURCE_SHA256` /
`FLAG_SOURCE_SHA256`) are unchanged, so only `lua_record_probe.py`
`TARGET_SHA256` moved to the fresh x64 EXE
(`37c02a22bff3c1b46033e7ff8ef37338fb3f8c8fa70f8b5e6e3bb0fab1567421`).
`hook_probe.py` pins no target hash by design (name-attach, the hash
is recorded in the report evidence). A read-only pre-flight spawn
proved the fresh child before the re-pin: the metadata line contract
(pid / entry / result / calls, all integers), the unique 8-byte entry
pattern on disk (file offset `0x22e00`, RVA `0x26000` in `.tfnhook`)
read back through the child's own reported entry address, the packed
export pair (`fixture_result` RVA `0x22bc0`, `fixture_calls` RVA
`0x22bc4` from the on-disk export directory) and one common implied
image base across all three metadata addresses, with live callers
observed at `result=4`, `calls>20`; the `TARGET_SHA256` hash gate
still bounds every acceptance, so a future rebuild with a different
entry or protocol is refused before any child spawn.

Re-run through the source-runtime launcher (dev venv python,
`PYTHONPATH=src`, `ct2trainer.native.launcher.main` with `--plan` /
`--hook-fixture-target` / `--hook-fixture-report` and then `--plan` /
`--lua-fixture-target` / `--lua-fixture-report`, both exit 0), plans +
reports under `build\windows-fixture\hook-check-20261115T135250Z\`
(git-ignored; hook plan file sha256
`9234138b05e8337998255c32cbc7bacf467a7e3592c68ea8dd468e48346268dc`,
canonical plan sha256
`63b98c5ac105e5969d396bd2b0f629316189802e97515a9751df708db177bfcd`,
2/2 supported; Lua plan file sha256
`e15ec3481ba048c08e6788a444c408ba5acd2c5f4afdafe5dc0a4b2f91d5f30c`,
canonical plan sha256
`620f96597653151e1a69d235bc9a8ad15505c9e4012146f94c2986d08570433e`,
2/2 supported, `validate_fixture_plan` OK):

- Hook report `ct2trainer-frozen-hook/v1` status `passed`,
  `frozen_runtime: false`, `ce_inputs: []` - 7/7 checks passed:
  remote-export-value-address-and-original-effect,
  embedded-ct-nasm-iced-debugger-hook-confirmed-and-saved,
  embedded-upstream-lua53-record-write-independent-readback,
  exact-disable-effect-and-saved-wish-cleared,
  retired-cave-remains-readable-before-target-exit,
  exact-target-exit-finalizes-retained-code,
  controller-state-ownership-released
  (`game_unverified: true` stays set per gate).
- Lua report `ct2trainer-frozen-lua-record/v1` status `passed`,
  `frozen_runtime: false`, `ce_inputs: []` - 4/4 checks passed:
  ct_compiler_to_automatic_lua_receipts_owned_write_and_cooperative_worker,
  scoped_code_data_provider_and_dependency_refusal_before_cancellation,
  disable_lua_owned_receipt_main_inverse_raw_undo_and_callback_cancellation,
  fresh_activation_exact_target_exit_finalization_and_confirmed_saved_state_restart.

## Verified frozen hook + Lua-record gates (2026-11-24, 0.52.2
build cut)

Both frozen gates (the generated trainers, `frozen_runtime: true`)
were re-run at the 0.52.2 release cut (run
`native-20261124T033652Z-1da5b40e`, cut from `main` @ `cbbd386`): the
two frozen trainers regenerated from the gate-passed plans with the
0.52.2 template stub (sha256
`20c17ee135c9bfb388612ade31e1cad5ee032768044f29d4099344017c34ce25`) -
frozen hook trainer sha256
`39425a0fcd2af08229729258956fa7f8b5d8c7f8193fe589fe6987a262fe5c31`,
frozen Lua-record trainer sha256
`ba487ef5c0441ab3ad49c44b851c84e37cbeefc36f0eb673b26fd6aea9459ff1`,
embedded plan identity identical to the source runtime (plan sha256
`63b98c5ac105e5969d396bd2b0f629316189802e97515a9751df708db177bfcd`
hook, `620f96597653151e1a69d235bc9a8ad15505c9e4012146f94c2986d08570433e`
Lua-record) - against the rebuilt shared target (sha256
`0f32e7d18670cb3eb3c95723f13e7d11c1742205c5988f8166784865ab9831a6`,
rebuilt from the unchanged source into
`build\runs\native-hook-fixture-20261124T031403Z-76b8c44b\`): each
ran with its `--hook-fixture-target` / `--hook-fixture-report` or
`--lua-fixture-target` / `--lua-fixture-report` pair (exit 0)
against the shared live `NativeHookFixture.exe` target it spawned
itself: hook report `ct2trainer-frozen-hook/v1` status `passed`,
`frozen_runtime: true`, 7/7 checks; Lua report
`ct2trainer-frozen-lua-record/v1` status `passed`,
`frozen_runtime: true`, 4/4 checks. Evidence under the git-ignored
`build\windows-fixture\frozen-check-20261124T040411Z\`. This record
closes the hook / Lua-record fixture portion of the Windows runtime
evidence only: real-game, clean-machine and Deck / Proton acceptance
remain open (`runtime_unverified` stays set).
