# Owned code-patch fixture

This subtree is independently authored test material. It contains no CE
input, game table, injection or executable callback beyond the pinned
sentinels the trainer's code-patch records manage under test. It is
ignored evidence. Its first-party source is promoted and included in the
Native source-export allowlist. Compiled target hashes and actual runtime
evidence are recorded separately; a fresh C build does not inherit
another binary's runtime proof.

`codepatch_target.c` is the deterministic code-patch target
(`NativeCodePatchFixture.exe`, built for x64 and x86). The layout
contract is byte-pinned and shared with the pinned CTs and the gate:

- The 16-byte module marker `CT2T-CPP-2026-01`
  (`435432542d4350502d323032362d3031`) occurs exactly once.
- `data_a` holds the 8-byte baseline `DATA_A01`
  (`444154415f413031`); its tail four bytes (offset +4, baseline `_A01`
  `5F413031`) are the overlap block the refusal-target record
  addresses.
- `data_b` holds the 4-byte baseline `DATB` (`44415442`).
- `codepatch_probe()` returns the fixed constant `0x5A5B5C5D`. MSVC
  `/Od` emits it as `B8 5D 5C 5B 5A C3` (x64) or
  `55 8B EC B8 5D 5C 5B 5A 5D C3` (x86, extra frame pointer setup); the
  CTs patch the entry so it returns `0x46474849` instead, and the
  target's own protocol loop executes the patched entry on every
  `probe` reply.
- The `setdata A|B <hex>` protocol commands let the owned gate modify a
  data block from the target itself (simulating an external writer);
  every command replies with the status line.

The first stdout line carries the bounded JSON metadata contract
(`ct2trainer-owned-codepatch-target/v1`) with the exact integer key set
`{"schema","pid","pointer_bits","pe_machine","process_name",
"module_base","module_bytes","page_bytes","marker_rva","marker_bytes",
"data_a_rva","data_a_bytes","data_b_rva","data_b_bytes","overlap_rva",
"overlap_bytes","probe_rva","probe_bytes","original_value"}`; the
sentinel bytes are the pinned constants in lowercase hex. Protocol
commands: `probe` (status JSON
`ct2trainer-owned-codepatch-status/v1` with the sequence number and the
probe value the live entry returns) and `quit` (exit 0). Any other
command exits 7.

Two gate tables target it (`tests/fixtures/codepatch/`):

- `codepatch_x64.ct` (4 `<CodeEntry>` records, x64): record 1 patches
  `data_a` to `PATCHEd0` (`5041544348454430`); record 2 patches the
  probe entry to return `0x46474849`; record 3 patches `data_b` to
  `P4TB` (`50415442`); record 4 patches the `data_a` tail (overlap
  block) to `C003` (`43303033`) and is the overlap-refusal target while
  record 1 is applied.
- `codepatch_x86.ct` (4 records, x86): the same four patches against
  the 32-bit target image (frame-setup probe prologue).

`Invoke-CodePatchFixtureBuild.ps1 -OutputDirectory <fresh-path>`
(architectures default to both) creates source snapshots (target
source, this build script) and the `NativeCodePatchFixture.exe` targets
with MSVC `/W4 /WX /Od`, verifying the PE machine per architecture,
that the 16-byte marker, both data baselines and the probe prologue
each occur exactly once, and preserving the compiler command, version
and path logs. It writes `build.json` evidence (schema
`ct2trainer-owned-codepatch-build/v1`) with byte-pinned SHA-256 per
architecture. The CTs are pinned by the gate itself (the gate validates
the plan against the exact CT hashes and canonical plan fingerprints
before any child spawn); a successful build alone does not prove the
gate - runtime evidence must also check exact target identity, the
data-page publish/capture/restore lifecycle, the overlap and
target-changed refusals, the already-active adoption, the
executable-page routing through the verified hook coordinator, the
restore-mismatch engine block with its blocked-session close fence,
target-exit finalization of the blocked session, saved-ON replay of
both routes on a fresh identity, replayed disables and the recorded
live-close fence (refusal with all receipts retained).

The gate is controller-only: it is driven through
`codepatch_probe.run_probe(plan, target, report)` (the report file is
opened `'x'` and must be fresh) or through the frozen/source launcher
pair `--codepatch-fixture-target` / `--codepatch-fixture-report`. An
orphan flag or a mixed gate is refused before the plan is read; a
frozen embedded-plan failure exits 2 without reserving a report. The
state directories are created inside the gate (`tempfile.mkdtemp`).

## Verified owned code-patch gate (2026-11-16, source runtime, x64)

First recorded pass, repo `main` @ `a4e805d` (0.52.1 closed; the
code-patch lane is not committed at measurement time) on Windows
`Microsoft Windows NT 10.0.26300.0` x64 (PowerShell 5.1.26100.9818),
dev venv python with `PYTHONPATH=src` as the source-runtime
interpreter. Both targets built from the owned source
(`codepatch_target.c` sha256
`89f1bef4b4f59fbd6653bd9eb1ff6777d321c740bde30d2741f7af56fe7a52e9`,
7,679 bytes; recipe sha256
`27f627e804c33f8214f3a6203ee90c75dad67dfa493c23224019413f7ef1c27d`)
with MSVC `cl.exe` 19.44.35229 (BuildTools 2022, `/W4 /WX /Od`) through
this directory's committed recipe `Invoke-CodePatchFixtureBuild.ps1`
(x64 + x86) into run
`build\runs\native-codepatch-fixture-20261116T032022Z-bdd3\`
(git-ignored): `build.json` (schema
`ct2trainer-owned-codepatch-build/v1`) status `passed`, `ce_inputs: []`,
x64 EXE sha256
`3f217da553159221216db43c6c8e83481d5da2869edcdf68ca4f66980a9b891f`
(147,456 bytes, PE machine 0x8664, marker/data_a/data_b/probe
occurrence 1 each), x86 EXE sha256
`288855467feab361c2d27a64a4ff68bb73687923d8e3984003a3c7fe77ae6a85`
(PE machine 0x14C, same occurrence proof). The x64 RVAs were measured
from the live target's metadata line (marker 0x18350, data_a 0x23000,
data_b 0x23008, overlap 0x23004 = data_a + 4, probe 0x11F0); the x86
RVAs were measured statically by a PE section walk cross-proven
byte-exact against the x64 runtime metadata (marker 0x16190, data_a
0x1D000, data_b 0x1D008, overlap 0x1D004, probe 0x11A0).

Both pinned CTs compile to the pinned canonical plans (4
supported/selected `code_patch` records each, zero blocks/warnings,
counts `{total: 4, supported: 4, actionable: 0, blocked: 0,
headings: 0}`): `codepatch_x64.ct` sha256
`3219ee42a0cab3f40a66fce762c62c6e0b49140e91fcff671759e8354d78bc31`
(1,226 bytes, trainer_id `bbafd3e7ad4b1731`, canonical plan
fingerprint `6b0ce466529127e1497cc1e47e7ca4d3bbaba198564c1bbb701b4c57155cffa3`,
plan file sha256
`cef82a71b2cf082a7764f0fd203a47634106468001f3a0eee5496e1dde9360c8`),
`codepatch_x86.ct` sha256
`de7be66c3ef09747a7a475539aed9afc2c77af0affb0e8d5ee4aaa50d61369d8`
(1,242 bytes, canonical plan fingerprint
`c67846921cafeedb36387e465efa88fdaa95e80c7526bc485df817b8d6a28061`).
A read-only pre-flight spawn proved both fresh children before the
pins: the bounded metadata line contract (exact key set, integer
keys, exact sentinel hex, `overlap_rva == data_a_rva + 4`), the
sentinel bytes at their RVAs read back byte-exact through
independent `OpenProcess` / `ReadProcessMemory`, one `probe` status
reply (`sequence=1`, `probe_value=0x5A5B5C5D`) and the `quit` exit 0;
the `TARGET_SHA256` hash gate still bounds every acceptance, so a
future rebuild with a different layout or protocol is refused before
any child spawn.

Re-run through the source-runtime launcher
(`--plan <compiled plan> --codepatch-fixture-target <pinned x64 EXE>
--codepatch-fixture-report <fresh report>`; plan file sha256
`cef82a71b2cf082a7764f0fd203a47634106468001f3a0eee5496e1dde9360c8`;
plan + report under `build\windows-fixture\codepatch-check-20261116T082357Z\`,
git-ignored):

- x64 report `ct2trainer-owned-codepatch/v1` status `passed`,
  `source_runtime: true`, `frozen_runtime: false`,
  `ce_implementation_inputs: []`, `owned_markers_absent: true`,
  launcher exit 0 - 14/14 checks passed:
  exact-child-image-identity-architecture-and-module-metadata,
  baseline-data-exec-and-marker-sentinels,
  data-enable-publishes-actual-and-captures-original,
  overlapping-code-patch-refused-zero-write,
  data-disable-restores-captured-original,
  target-changed-refusal-zero-write,
  already-active-adopts-and-no-write-disable,
  exec-enable-patches-live-function-and-target-executes,
  restore-mismatch-keeps-record-applied-and-blocks-engine,
  blocked-engine-refuses-actions-and-second-controller,
  target-exit-close-finalizes-blocked-session-and-persists-wishes,
  saved-on-replays-both-routes-on-fresh-identity,
  replayed-disables-restore-originals-and-target-reverts,
  normal-close-after-exit-confirms-cleanup; plus the recorded
  live-close fence (a blocked live close on a third owned target
  refused with a `False` return and the exact reason "code-patch
  restore mismatch: bytes at 0x... changed externally; refusing to
  overwrite foreign bytes", the patched entry and the foreign data
  block left untouched, and `state.lock` / `session.json` /
  `state.json` (both saved wishes) / the `enabled`-state executable
  journal all preserved across the subsequent target exit).
- x86: **machine-gated pending** - the fresh unsigned x86 target fails
  `CreateProcess` with WinError 740 (Smart App Control first-launch
  review; prior x86 fixture binaries launch fine from Python, so the
  block is the first-launch review of this specific binary, not a
  machine-wide x86 restriction). The x86 pins are static-verified
  (target hash, PE machine via the independent bounded header
  re-check, plan fingerprint, RVAs cross-proven against the x64
  runtime metadata), and the engine semantics are architecture-neutral
  (the x64 run proves every check except the architecture-specific
  probe prologue bytes and RVAs, which are byte-pinned). The x86
  source-runtime run is to be recorded after the pending SAC prompt is
  approved, or together with the frozen re-run.

The frozen re-run (the generated trainers, `frozen_runtime: true`) of
both architectures happens at the next release cut, following the
eight-lane precedent; until then this record plus the x86
machine-gate note are the interim Windows runtime evidence for the
code-patch gate. Real-game, clean-machine and Deck / Proton / touch
acceptance remain open (`runtime_unverified` stays set).
