# Owned String fixture

This subtree is independently authored test material. It contains no CE input,
game table, injection, hook installation or executable callback. It is ignored
evidence. Its first-party source is promoted and included in the Native source-
export allowlist. Compiled target hashes and actual runtime evidence are recorded
separately; a fresh C build does not inherit another binary's runtime proof.

`Invoke-StringFixtureBuild.ps1 -OutputDirectory <fresh-path>` builds a source
snapshot and `NativeStringFixture.exe` in separate x64/x86 directories with
MSVC `/W4 /WX /Od /TC` and a nonincremental link. Failures and compiler command,
version and path logs remain in the fresh output. The successful `build-1`
snapshot is immutable evidence; rebuild into a different output directory.

## JSON-lines protocol

The first stdout line has schema `ct2trainer-owned-string-target/v1`.
It includes PID, pointer width, PE machine, executable name, main-image base and
`SizeOfImage` read from the child's own PE header. The child does not declare a
trusted creation identity; the controller must independently query identity and
bind the exact executable/source hash.

The `buffers` address map has `ascii`, `utf16` and `fixed`. Each exposes absolute
address and RVA, encoded-unit length, unit size, complete declared read span,
full guarded span, before/after addresses and RVAs, and eight guard bytes on
either side. The globals are distinct committed `PAGE_READWRITE` image data.
These guards are ordinary sentinel bytes, not Windows `PAGE_GUARD` pages.

| Buffer | Declared span | Initial bytes / visible text | Tail |
| --- | --- | --- | --- |
| `ascii` | 8 bytes | `old\0QRST`, visible `old` | Offset 4, four untouched declared-tail bytes |
| `utf16` | 16 UTF-16 units / 32 bytes | `OLD`, valid `D83D DE42` pair, aligned NUL | Offset 12, ten tail units; the first is deliberately invalid lone `DEAD` |
| `fixed` | 8 bytes, no terminator semantics | `FI\0XED!?`, embedded NUL is literal | `tail_offset == read_bytes`; every byte belongs to the fixed value |

`readonly` and `executable` describe separate owned private pages containing
eight observable bytes. Their actual protections are `PAGE_READONLY` (2) and
`PAGE_EXECUTE_READWRITE` (64). No executable page is called. Each also exposes a
module-relative pointer-slot RVA, allowing a controller to derive the target
address from `[(module base) + pointer_rva]` at the correct pointer width.
Both are intended negative String-write admission cases; this local fixture
verification establishes the protections, not runtime refusal behavior.

Accepted stdin lines are `status`, `mutate-prefix`, `mutate-tail` and `quit`.
LF and CRLF are accepted. Unknown input exits with a failure. Each status or
mutation returns one `ct2trainer-owned-string-status/v1` line with PID,
command sequence, hexadecimal full value and guard bytes, and actual queried
memory-region attributes. Output contains no decoded string assumptions.

`mutate-prefix` changes only the first byte/unit of each buffer to `M`.
`mutate-tail` toggles the low bit of the final byte/unit in each buffer. For
ASCII/UTF-16 this is the ignored declared tail. For `fixed` it is an owned
literal byte that a fixed-string freeze should restore. Guards and negative
pages are unaffected. There are no background target writers; after each
command the main thread waits for the next stdin line. `quit` releases both
owned private pages and exits normally.

## Independent local proof

Run `verify_string_fixture.py --build <build-path> --output <fresh-path>` using
the archived Windows Python. It launches exact hash-checked new children one
at a time with hidden windows, opens only VM_READ/QUERY_INFORMATION rights,
queries image identity and creation FILETIME, compares local/remote PE fields,
reads every full guarded buffer and private pointer slot, checks protections,
issues the explicit local mutation commands, and observes normal exits.
It never uses WriteProcessMemory, changes remote protection, or acquires a
debug-event proof. Its JSON/logs are retained even if a check fails.

`runtime-1/verification.json` records 29 successful checks per architecture.
This proves owned target layout/protocol/read observations only. The String
controller still needs source/identity binding, held-event publication,
precise literal-prefix write/undo and tail preservation, overlap and freeze
policy, refusal of read-only/executable/incomplete spans, and failure/late-guard
tests before source/frozen trainer acceptance can be claimed.

## Verified String gate (2026-11-15, source runtime)

Pass 1 of the owned String gate, repo `main` @ `3519dcd` (post-0.52) on
Windows `Microsoft Windows NT 10.0.26300.0` x64. The 2026-10-07 repin build
`build/runs/fixture-repin-20261007T115729Z` had been cleaned, so the fixture
was rebuilt from the unchanged source (`string_target.c` sha256
`9c69ea3549387956551e96d501a5184765d59df36cae2cc32936ca81b0877652`, single
git commit) with the same MSVC `cl.exe` 19.44.35229 (BuildTools 2022,
`/W4 /WX /Od /TC`, nonincremental link) - fresh run
`build\runs\native-string-fixture-20261115T085726Z-b2cade29\`
(git-ignored), `verification.json` status `passed`. The fresh builds are
byte-nondeterministic (two independent rebuilds produced different hashes
for both architectures), so `string_probe.py` `TARGET_SHA256` was re-pinned to
the fresh EXEs (documented re-pin practice, as for the scan lane).

Layout outcome of the rebuild (proved by the children's own
`ct2trainer-owned-string-target/v1` metadata, two independent rebuilds in
agreement):

- x64: identical to the 2026-10-07 layout (`module_bytes` `0x2A000`,
  ascii/utf16/fixed/readonly/executable RVAs unchanged) - the x64 CT is
  unchanged (sha256
  `97e36a533db823542bed0830cd07a0eaedc8b1f34ff36d108c2c3edf69e3c10e`) and the
  freshly compiled x64 plan fingerprint is byte-identical to the pinned
  `fc1ff36bcfa1bba926cf792a0e62ec619aaaa21866f424a19cbe4d2bb07c59f8`,
  confirming compiler determinism.
- x86: the static data block sits a uniform 0x40 lower than the 2026-10-07
  build (ascii `0x1DE40` -> `0x1DE00`, utf16 `0x1DE58` -> `0x1DE18`,
  fixed `0x1DE88` -> `0x1DE48`, readonly pointer `0x1DE98` -> `0x1DE58`,
  executable pointer `0x1DE9C` -> `0x1DE5C`; `module_bytes` unchanged at
  `0x22000`, the guarded-buffer spacing and pointer-slot layout are
  unchanged). The x86 CT addresses were re-pinned to the fresh layout
  (all six records, incl. the prefix-overlap byte at ascii+1), the probe
  `LAYOUT['x86']` moved with them, and the new pins are CT sha256
  `95e30b8ef100e16414b43d916e1d70ef025131433fd8847fea50f0dc170ff984` and
  plan fingerprint
  `e49036db5a725a08ebaa3e499a74e9dde4913b2d5265a9cf070912f5312c6640`.
  The hash gate (`TARGET_SHA256`) still bounds every acceptance, so a
  future rebuild with a different layout is refused before any child
  spawn, never mis-tested.

Re-run through the source-runtime launcher (0.52 in-build venv python,
`PYTHONPATH=src`, `ct2trainer.native.launcher.main` with `--plan` /
`--string-fixture-target` / `--string-fixture-report`, exit 0), plans +
reports under
`build\windows-fixture\string-check-20261115T095000Z-string\` (git-ignored):

- x64: report `ct2trainer-owned-string/v1` status `passed`,
  `frozen_runtime: false`, `ce_inputs: []`,
  `owned_markers_absent: true` - 14/14 checks passed:
  exact-child-image-identity-architecture-regions-rvas-and-sentinels,
  real-ascii-utf16-surrogate-and-fixed-embedded-zero-reads,
  invalid-encoding-length-and-nul-refuse-before-effect,
  ascii-precise-prefix-held-write-retains-declared-tail-and-guards,
  utf16-units-surrogate-and-aligned-terminator-write-preserves-tail,
  fixed-literal-exact-units-including-embedded-zero,
  read-only-and-rwx-regions-refuse-without-changing-bytes-or-protection,
  freeze-preserves-new-unowned-tails-and-restores-fixed-owned-last-byte,
  fresh-held-freeze-repairs-owned-prefix-only-with-independent-readback,
  frozen-prefix-overlap-refuses-before-effect,
  apply-updates-variable-length-freeze-intent-without-stale-tail-replay,
  live-controller-restart-drops-freeze-and-never-saves-or-replays-string-values,
  target-pid-creation-restart-attaches-fresh-without-value-or-freeze-replay,
  normal-final-close-sentinels-markers-and-owned-target-exit.
- x86: same 14/14 pass against the re-pinned x86 target
  (`3c22495e86ace0999b64f10d35e2c276d753d62667daa2347077cc76009f5ab7`),
  `target_architecture: x86`, `frozen_runtime: false`.

## Re-pin before the 0.52.1 cut (2026-11-15, source runtime)

The string lane's pin build was cleaned before the 0.52.1 release cut,
so the fixture was rebuilt a second time from the same unchanged source
(`string_target.c` sha256
`9c69ea3549387956551e96d501a5184765d59df36cae2cc32936ca81b0877652`,
MSVC `cl.exe` 19.44.35229, `/W4 /WX /Od /TC`, nonincremental link) into
`build\runs\native-string-fixture-20261115T174324Z-45f4\`
(git-ignored), `verification.json` (schema
`ct2trainer-owned-string-build/v1`) status `passed`, `ce_inputs: []`.
`string_probe.py` `TARGET_SHA256` moved again to the fresh EXEs (x64
`7b815ff5148180b434a7ebe543411b54e4d5ce90399ed83e4bf8ecc5f77eb0fd`,
x86 `7876bf70a8feab52a5774802708d82f1eab36f435231ba3045c59a7b7a7f0668`);
both pinned CTs are unchanged and the canonical plan fingerprints
(`PLAN_SHA256`) still hold against the freshly compiled plans, so no
compiler drift. Both gates re-ran through the source-runtime launcher
against the fresh targets, plans + reports under
`build\windows-fixture\string-check-20261115T175237Z\` (git-ignored):
both `ct2trainer-owned-string/v1` status `passed`, 14/14 checks per
architecture, `source_runtime: true`, `ce_inputs: []`,
`owned_markers_absent: true`.

## Verified frozen String gate (2026-11-15, 0.52.1 build cut)

Both frozen String gates (`frozen_runtime: true`, the generated
string trainers) were re-run at the 0.52.1 release cut (run
`native-20261115T181026Z-00f5dfe8`, cut from `main` @ `dc138e0`): the
two frozen trainers regenerated from the gate-passed plans with the
0.52.1 template stub (sha256
`df004f1afeea2d73fffe1747bb24e8139318311ac59893ea65759a9bf365e040`) -
frozen x64 trainer sha256
`7943372c45f2521b93f65ecbe952ef387efa3612e4907b51fa899291e4120bcc`
(plan sha256
`c0299324e87d1c47cc4fc3f39b9e1a9e90523bd85b0713f1ce6451548923c0f2`),
frozen x86 trainer sha256
`e225c9adc45997a820ef0871341a087d1a0c5b885c645c4954e6a7f7e5d238b5`
(plan sha256
`c8af1df0086741635f8d252f5d0269729fe58574a0c91d3b7aa30feb571c5643`) -
each ran with `--string-fixture-target` / `--string-fixture-report`
(exit 0) against the live owned target it spawned itself: both
reports `ct2trainer-owned-string/v1` status `passed`,
`frozen_runtime: true`, 14/14 checks each. Evidence under the
git-ignored `build\windows-fixture\frozen-check-20261115T183206Z\`.
This record closes the String-fixture portion of the Windows runtime
evidence only: real-game, clean-machine and Deck / Proton acceptance
remain open (`runtime_unverified` stays set).

The module/RVA interpretation follows the public Microsoft
[PE format](https://learn.microsoft.com/en-us/windows/win32/debug/pe-format).
