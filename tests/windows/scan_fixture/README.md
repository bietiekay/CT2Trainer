# Owned process and nth scan fixture

This independently authored C target provides one 32-byte pattern in a private
RW allocation and three 16-byte patterns in its main image. `add-first` adds an
earlier module occurrence while a trainer is active: disable must use its captured
address. All patterns are initialized by the target itself. There is no injection,
game dependency or CE implementation input.

`Invoke-ScanFixtureBuild.ps1` creates fresh x64/x86 builds with source snapshots,
compiler logs, PE architecture and output hashes. A successful build alone does
not prove scan, trainer publication or game compatibility. Runtime evidence must
also check exact target identity, independent readback, complete matches, unchanged
context/sentinels, disable, saved reattach and actual frozen output.

The child accepts only `status`, `add-first` and `quit` on standard input; it
prints bounded JSON metadata/results on standard output. Close input exits normally.

## Verified scan gate (2026-11-15, source runtime)

First pass of the owned process/nth scan gate, repo `main` @ `a017d5e`
plus the owned luacall binding lane (this change) on Windows
`Microsoft Windows NT 10.0.26300.0` x64 (PowerShell
5.1.26100.9818). The pre-0.51 repin build
`build/runs/fixture-repin-20261007T115729Z` had been cleaned, so the
fixture was rebuilt from the unchanged source (`scan_target.c` sha256
`4c939ab3c42aeea7eb2211253af8f7bbb374646afd12d744d06685bb7b72808f`,
single git commit `b6c48cc`; the CT is unchanged at sha256
`440a5bf3fdaaae5e2756eed16f8728efd3c65c7c40084e2a0685f2e2c83366db`)
with the same MSVC `cl.exe` 19.44.35229 (BuildTools 2022,
`/W4 /WX /Od /TC`, `/INCREMENTAL:NO`) - fresh run
`build\runs\native-scan-fixture-20261115T043627Z-cfea6da9\`
(git-ignored), `verification.json` status `passed`, `ce_inputs: []`,
`runtime_verified: false`: x64 `NativeScanFixture.exe` sha256
`e54b12801564aed37ad9ee3ed3283459e53f9f69ee8042af73730fc0784c5315`
(PE `0x8664`) and x86 `NativeScanFixture.exe` sha256
`d66756a12c741caf163823a26643bce5c0a0369c8b689fc00f0a3f52fa8a626e`
(PE `0x014C`); `scan_probe.py` re-pinned to the fresh hashes
(documented re-pin practice).

The first x64 gate run (pre-owned-binding, 0.51 content) advanced the
exact-arch/patterns and compact-process-scan checks and then failed
the open luacall gate: record 2 was refused visibly with
`no luacall binding factory` (fail-closed, no allocation or write).
The owned luacall binding
(`src/ct2trainer/native/luacall_binding.py` - `OwnedNthAobPort` on the
engine's attached target memory, module-bounded / 1-based occurrence /
identity-checked / read-only; `OwnedLuaCallBinding` covering exactly
`lua_aobscan` / `ct2trainerNthAOB`;
`owned_luacall_binding_factory`) wired at the trainer, Master and
scan-probe construction sites closed the gate. Re-run through the
source-runtime launcher (0.51 in-build venv python, sha256
`5fc3c5244b5eef01a82fbefd1932d1382b79c72fe6e64ffe8df1e3ce3643f02f`,
`ct2trainer.native.launcher.main` with `--plan` /
`--scan-fixture-target` / `--scan-fixture-report`, exit 0), plans +
frozen scan trainers under
`build\windows-fixture\scan-check-20261115T044000Z-scan\`
(git-ignored; x64 plan sha256
`1a84220daa1d98f62668ea1c7761e703e0229de2ea19b1952df9b11fe4b086e5`,
x86 plan sha256
`fa1939cd1213f3471cb1f6fcca97644c048b3f1c23d8a503adbdc6eb9b09554a`):

- x64 report `ct2trainer-owned-scan/v1` status `passed`,
  `frozen_runtime: false`, `ce_inputs: []`,
  `owned_markers_absent: true` - 8/8 checks passed:
  exact-architecture-target-and-three-module-patterns-with-private-buffer,
  compact-process-scan-real-held-publication-and-independent-readback,
  nth-module-source-adapter-confirmed-and-journaled,
  earlier-new-match-does-not-rebind-disable-and-both-scopes-restore-exactly,
  fresh-reactivation-rescans-and-saves-current-occurrence,
  target-restart-reapplies-confirmed-wishes-to-fresh-captured-addresses,
  controller-restart-restores-saved-confirmed-records,
  final-off-and-normal-target-cleanup. Terminal receipts in schema-valid
  terminal states (1 `target-exited`, 3 `abandoned`); the nth scan is
  module-bounded (three module occurrences, `add-first` adds an earlier
  one while active) and journaled per receipt.
- x86 report: same 8/8 pass against the fresh x86 target
  (`d66756a1...`), `target_architecture: x86`, `frozen_runtime: false`.

The frozen scan gate (`frozen_runtime: true`, the generated
`ScanTrainer.exe`) was re-run at the 0.52.2 release cut - see
"Verified frozen scan gate (2026-11-24, 0.52.2 build cut)" below.
This record closes the scan-fixture portion of the Windows runtime
evidence only: real-game, clean-machine and Deck / Proton acceptance
remain open (`runtime_unverified` stays set).

## Verified frozen scan gate (2026-11-24, 0.52.2 build cut)

At the 0.52.2 release cut (run
`native-20261124T033652Z-1da5b40e`, cut from `main` @ `cbbd386`,
2026-11-24), the two frozen scan trainers were regenerated from the
gate-passed `plan.json` files with the 0.52.2 template stub (sha256
`20c17ee135c9bfb388612ade31e1cad5ee032768044f29d4099344017c34ce25` -
both `.build.json` reports confirm the new template identity) and
re-run against the rebuilt fixture targets (x64
`NativeScanFixture.exe` sha256
`67b2e56acee6a9d55948d640700be670ae319c90a0fe97629bfa2880697bfb9d`,
x86 sha256
`a9f25c099334459022f22f0caa361713b1797e058882e053cd34398d345b3f15`,
rebuilt from the unchanged source into
`build\runs\native-scan-fixture-20261124T031403Z-76b8c44b\`; the CT
unchanged at sha256
`440a5bf3fdaaae5e2756eed16f8728efd3c65c7c40084e2a0685f2e2c83366db`):

- x64: frozen `ScanTrainer.exe` sha256
  `8f7cabdbe773f05e90a536af8ba508c843eb05e76667c3597e3b16e3f8e10694`
  (16,945,727 bytes); embedded plan sha256
  `20341aaaf462d720f7596856c64b22f23d82e2e0af98a6dc7fae6e7a7bd66b81`;
  report `ct2trainer-owned-scan/v1` status `passed`,
  `frozen_runtime: true`, `ce_inputs: []`,
  `owned_markers_absent: true` - 8/8 checks passed, the same check
  set as the source-runtime record above.
- x86: frozen `ScanTrainer.exe` sha256
  `b32146ffeec23c0a121f79a06a59698e1673d23511afdc12d2d1810b0685f790`
  (16,945,727 bytes); embedded plan sha256
  `eb7366efbb471432deccc16e18bb9d7942964eef4fe09e6069f99056292fbafe`;
  report `ct2trainer-owned-scan/v1` status `passed`,
  `frozen_runtime: true`, `ce_inputs: []`,
  `owned_markers_absent: true` - 8/8 checks passed. The first
  attempt of this run was interrupted by a transient orphan
  `NativeScanFixture.exe` from an earlier source check (the gate
  refused with "expected exactly one fixture target, found 2");
  the retry on a clean process table passed as recorded here.

Evidence under the git-ignored
`build\windows-fixture\frozen-check-20261124T040411Z\`. This closes
the frozen scan gate at the 0.52.2 build cut. Real-game,
clean-machine and Deck / Proton / touch acceptance remain open
(`runtime_unverified` stays set per
`documentation/native-verification.md` section 5 and the roadmap
RT-6 acceptance).
