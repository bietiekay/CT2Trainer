# Owned global-allocation fixture

This subtree is independently authored test material. It contains no CE
input, game table, injection or executable callback beyond the owned
global allocation the trainer manages under test. It is ignored
evidence. Its first-party source is promoted and included in the Native
source-export allowlist. Compiled target hashes and actual runtime
evidence are recorded separately; a fresh C build does not inherit
another binary's runtime proof.

`global_target.c` is the deterministic Global-allocation target
(`NativeGlobalFixture.exe`, built for x64 and x86). The layout contract
is byte-pinned and shared with the pinned CTs and the gate:

- `global_state.marker` holds the unique 16-byte module anchor
  `CT2T-GLB-2026-01`; the CTs locate it with `aobscanmodule`.
- `global_probe()` returns the fixed constant `0x5A5B5C5D`. MSVC `/Od`
  emits it as `B8 5D 5C 5B 5A C3` (x64) or
  `55 8B EC B8 5D 5C 5B 5A 5D C3` (x86, extra frame setup); the CTs
  patch the entry with a jump stub into a trainer-owned cave that reads
  the shared RW global and returns it.
- The first stdout line carries the bounded JSON metadata contract
  (`ct2trainer-owned-global-target/v1`) with the integer keys
  `{"schema","pid","pointer_bits","pe_machine","process_name",
  "module_base","module_bytes","page_bytes","marker_rva","marker_bytes",
  "probe_rva","probe_bytes","original_value"}`; the marker/probe bytes
  are the pinned sentinels in hex.
- Protocol commands: `probe` (status JSON
  `ct2trainer-owned-global-status/v1` with the sequence number and the
  probe value the live entry returns) and `quit` (exit 0). Any other
  command exits 7.

Two gate tables target it (`tests/fixtures/global_alloc/`):

- `global_alloc_x64.ct` (2 records, x64): record 1 is an AA script that
  `aobscanmodule`s the marker anchor and the probe entry, allocates the
  shared global `globalvalue` near the anchor, patches the entry to
  return the global, and initializes it to 333; record 2 is the 4-byte
  value record bound to the global symbol.
- `global_alloc_x86.ct` (2 records, x86): the same program against the
  32-bit target image (frame-setup prologue).

`Invoke-GlobalFixtureBuild.ps1 -OutputDirectory <fresh-path>`
(architectures default to both) creates source snapshots (target
source, this build script) and the `NativeGlobalFixture.exe` targets
with MSVC `/W4 /WX /Od`, verifying the PE machine per architecture,
that the 16-byte marker and the probe prologue each occur exactly once,
and preserving the compiler command, version and path logs. It writes
`build.json` evidence (schema `ct2trainer-owned-global-build/v1`) with
byte-pinned SHA-256 per architecture. The CTs are pinned by the gate
itself (the gate validates the plan against the exact CT hashes and
canonical plan fingerprints before any child spawn); a successful build
alone does not prove the gates - runtime evidence must also check exact
target identity, the shared-global lifecycle (near-marker RW
allocation, 333 initialization, value roundtrip, disable retention,
hidden symbol), the second-controller and stale-journal fences, target
exit retirement, fresh-session re-allocation and the live-close fence
(refusal with all receipts retained).

The gate is controller-only: it is driven through
`global_probe.run_probe(plan, target, report)` (the report file is
opened `'x'` and must be fresh), not through a launcher flag. The
state directories are created inside the gate (`tempfile.mkdtemp`).

## Verified owned global gates (2026-11-15, source runtime)

First recorded pass of both gates, repo `main` @ `992326c`
(post-hook + Lua-record lane; the 0.52 content set is code-identical,
so the dev venv python serves as the source-runtime interpreter with
`PYTHONPATH=src`) on Windows `Microsoft Windows NT 10.0.26300.0` x64
(PowerShell 5.1.26100.9818). The 2026-10-07 pin build had been
cleaned, so both targets were rebuilt from the unchanged source
(`global_target.c` sha256
`c44cbe404954678ca753f81b17f6d9c1c17d16558755a79bcb982a983ebec6aa`)
with the same MSVC `cl.exe` 19.44.35229 (BuildTools 2022,
`/W4 /WX /Od`) through this directory's committed recipe
`Invoke-GlobalFixtureBuild.ps1` (x64 + x86) into run
`build\runs\native-global-fixture-20261115T144546Z-f569\`
(git-ignored): `build.json` (schema
`ct2trainer-owned-global-build/v1`) status `passed`, `ce_inputs: []`,
x64 EXE sha256
`cd74ef9285309e95251eea5df3181c5134cf4c6487b0965629114a96a188387e`
(146,432 bytes, PE machine 0x8664, marker/probe occurrence 1 each),
x86 EXE sha256
`b69cc968997d1ede53176aaa6c8cdbfebe6deee7838b7f064270f6dc8530bc56`
(121,344 bytes, PE machine 0x14C, marker/probe occurrence 1 each).

The re-pin is hash-only: both pinned CTs are unchanged on disk
(`global_alloc_x64.ct` sha256
`a27eb49eb76b628c7e3c3703d1018f206f00feab5d5c6e46ea032f53c28f92f6`,
`global_alloc_x86.ct` sha256
`99fab3bdaa7c8beffddbad9a1345801c87127e4a5bb78f6afd3cec807b4be65c`)
and the fixture source is unchanged, so only
`global_probe.py` `TARGET_SHA256` moved for both architectures. The
canonical plan fingerprints (`PLAN_SHA256`) still hold - the compiled
plans match them byte-for-byte, so no compiler drift: x64
`cf8fdfbc77a91ae811ac12cc4c6e4ea797cc168948ae6298f4e473936c661c00`,
x86 `312a753e3df1e71ec8fdb652b98c2880cc5b895febd9aff28e3a8897903b9982`.
A read-only pre-flight spawn proved both fresh children before the
re-pin: the bounded metadata line contract (all integer keys, exact
sentinel hex), the marker bytes at `module_base + marker_rva` and the
probe prologue at `module_base + probe_rva` read back byte-exact
through independent `OpenProcess` / `ReadProcessMemory`, one `probe`
status reply (`sequence=1`, `probe_value=0x5A5B5C5D`) and the `quit`
exit 0; the `TARGET_SHA256` hash gate still bounds every acceptance,
so a future rebuild with a different layout or protocol is refused
before any child spawn.

Re-run through the source-runtime controller (dev venv python,
`PYTHONPATH=src`, `global_probe.run_probe(plan, target, report)` for
each architecture with fresh `'x'` reports; both plans compiled 2/2
supported - x64 plan file sha256
`1c42341c02f40934f76809c9b0d9b7d71163b4b240b6d858b006460c3213a881`,
x86 plan file sha256
`3a14a5ef5fe3d91b731aa915770c061f258fa1becefac7754584dced6bf6c099` -
plans + reports under `build\windows-fixture\global-check-20261115T145222Z\`,
git-ignored):

- x64 report `ct2trainer-owned-global/v1` status `passed`,
  `source_runtime: true`, `frozen_runtime: false`,
  `ce_implementation_inputs: []`, `owned_markers_absent: true` -
  14/14 checks passed: exact-child-image-identity-architecture-and
  module-metadata, baseline-probe-returns-pinned-original-constant,
  global-enable-allocates-rw-storage-near-marker-and-initializes-333,
  patched-entry-returns-held-global-value-through-real-code-path,
  value-record-write-through-symbol-lands-in-held-global-storage,
  disable-restores-entry-bytes-and-retains-global-storage,
  value-symbol-hidden-after-disable-while-storage-remains,
  second-controller-refuses-live-state-claim,
  target-exit-retires-pool-and-removes-terminal-receipt,
  normal-close-after-exit-confirms-cleanup,
  stale-pool-journal-alone-blocks-new-controller,
  fresh-spawn-attaches-fresh-identity-with-original-probe,
  fresh-session-enable-reallocates-global-and-roundtrip-succeeds,
  normal-final-close-sentinels-markers-and-owned-target-exit; plus the
  recorded live-close fence (refusal
  "Shared globals and their retired consumers remain owned until exact
  target exit. Preserve the session and receipts.", entry restored,
  storage retained, all markers preserved).
- x86 report `ct2trainer-owned-global/v1` status `passed`,
  `source_runtime: true`, `frozen_runtime: false`,
  `ce_implementation_inputs: []`, `owned_markers_absent: true` - the
  same 14/14 checks passed, plus the same recorded live-close fence.

## Verified frozen global gate (2026-11-24, 0.52.2 build cut)

Both frozen global gates (the generated trainers,
`frozen_runtime: true`) were re-run at the 0.52.2 release cut (run
`native-20261124T033652Z-1da5b40e`, cut from `main` @ `cbbd386`): the
two frozen trainers regenerated from the gate-passed plans with the
0.52.2 template stub (sha256
`20c17ee135c9bfb388612ade31e1cad5ee032768044f29d4099344017c34ce25`) -
frozen x64 trainer sha256
`b8ebc7e868be9482fe1d15c6f473ec5dd1dd91e00ceb4ccdd2e93a338c3a6ac3`
(embedded plan sha256
`bd89b62363e1800424a66efdf5f31b9459d5cc0ee7e9730a081d9773e8601865`,
plan identity identical to the source runtime and the 0.52.1 frozen
record), frozen x86 trainer sha256
`11e171e9be4a2b224839eadad0c05c5eba86093c92787755fd0a93e12193c9c6`
(embedded plan sha256
`2f443b73f0ab4e9b7a827f433a20fd4d248ec0f67f541b92553735e9f1af191e`,
plan identity identical) - against the rebuilt owned targets (x64
sha256
`757c00f7d0939eaba9233df94eb236a88cae01b60760d37e0eafc1b6907179d1`,
x86 sha256
`8d72d490c7967b4dbac811bf25e8f0b6c9d4060bb30fd3566e1d7403f6f41040`,
rebuilt from the unchanged source into
`build\runs\native-global-fixture-20261124T031403Z-76b8c44b\`; the
pinned CTs are unchanged, so only the target hashes moved): each ran
with `--global-fixture-target` / `--global-fixture-report` (exit 0)
against the live owned target it spawned itself: both reports
`ct2trainer-owned-global/v1` status `passed`, `frozen_runtime: true`,
14/14 checks each. Evidence under the git-ignored
`build\windows-fixture\frozen-check-20261124T040411Z\`. This record
closes the global-fixture portion of the Windows runtime evidence
only: real-game, clean-machine and Deck / Proton / touch acceptance
remain open (`runtime_unverified` stays set).
