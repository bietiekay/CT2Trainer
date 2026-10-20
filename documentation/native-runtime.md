# CT2Trainer: independent runtime and redistribution

Status: October 20, 2026 (0.16; full Wave 4 feature set plus post-release field fixes).

CT2Trainer independently implements the CT converter and Windows trainer.
Its build and exported source use no CE implementation, patched Lua DLL, resources,
stubs or drivers. 0.9.0-rc2 is a historical baseline. Full CT
compatibility and Windows/game/Deck acceptance remain required work, not
a reduced goal satisfied by fixture tests.

Structural script acceptance can still fail at an unavailable host API or
resolver; in particular it does not establish speedhack, Mono or IL2CPP
execution support. Measured attainment, open points and the verified
integration boundary are summarized in
[native-verification.md](native-verification.md) and
[native-semantic-denominator.md](native-semantic-denominator.md).
The 0.16 build includes the complete Wave 4 feature set and the post-release
WP-58 UI startup fix and Sinking City 2 activation-chain evidence. Its full
suite passed 3,398 tests with 25 expected skips. The 42/42 feature matrix is
measured over the 30-table synthetic corpus; the separate local-only static
catalog of the full real reference corpus has 2,698 of 117,624 plan entries blocked.
Static IL2CPP file analysis is available in the source CLI (`ct2trainer native
il2cpp`) and as a frozen binary adapter
(`--il2cpp-static-pe/--il2cpp-static-metadata/--il2cpp-static-report`);
both produce bounded read-only reports, and no live managed resolver is
claimed. The 2,617-test / 25-skip count is the historical 0.9.0-rc2 baseline.

## Permissive components and local maintenance

| Component | Pinned input | License | Actual use |
| --- | --- | --- | --- |
| NASM | 3.02 source and Windows executable | BSD-2-Clause | x86/x64 instruction encoding and flat binary linking at actual remote addresses |
| iced-x86 | 1.21.0 source and Windows Python wheel | MIT | Instruction boundaries and relocation-aware `reassemble` |
| Lupa / upstream Lua | Lupa 2.8, explicit `lupa.lua53` | MIT / MIT | Real Lua 5.3 language execution with independently authored host adapters |
| Python / Tcl / Tk | Archived Python 3.12.14 x64 | Their retained licenses | Controller, converter and trainer UI |
| Selected LibCpp2IL sources | Commit `b5ad444b82267cb1e4b88b8b373c008105bdea52` | MIT | Stdlib-Python adaptation of static PE/Metadata-v29 parsing; no live managed resolver |
| Selected Mono API sources | Commit `0cbf0e290c31adb476f9de0fa44b1d8829affa40` | Selected MIT declarations; original project LICENSE/PATENTS retained | Source-only own collector/42 typed direct exports; no Mono binary/import library, initialization or active managed trainer route |

Upstream sources, binary archives, URLs, versions, notices and SHA-256 pins are
under `dependencies/native/`. Builds install archived wheels with `--no-index`.
NASM's executable is checked before use; packed native components are checked
against the independently acquired archives. Source exports include the permissive
upstream source archives and owned test fixtures, and exclude the game corpus.
[NASM license](https://github.com/netwide-assembler/nasm/blob/nasm-3.02/LICENSE),
[iced-x86 license](https://github.com/icedland/iced/blob/v1.21.0/LICENSE.txt),
[Lupa license](https://github.com/scoder/lupa/blob/master/LICENSE.txt),
[Lua license](https://www.lua.org/license.html).

The user authorizes copying/forking these dependencies, purpose-specific changes
and library API changes when needed. Upstream submission is optional;
compatibility adaptation lives in this repository. A future fork must retain its
upstream pin, license, source, local patch set, build command and behavioral
regression tests.
The selected LibCpp2IL adaptation retains originals and `LOCAL-CHANGES.md` under
`dependencies/native/libcpp2il-static/`. It is separate from the fixed 0.6 inputs.
Our internal API may change with an explicit profile/schema version. CT behavior
and controller lifecycle, rather than upstream library API stability, are the
acceptance contract.

The independently authored allowlist has a scoped MIT grant in
[`CT2Trainer-MIT.txt`](../licenses/CT2Trainer-MIT.txt).
Third-party notices travel with source and binary output and inside trainers.
This grant does not cover external trainer code or user-supplied CT content.
A checksum records the chosen bytes; it is not a signature or a legal audit.

## Implemented behavior

| Capability | Current independent implementation |
| --- | --- |
| CT metadata | Bounded XML, IDs, hierarchy, source hash, explicit selection and capability reasons |
| Numeric values | Byte, 2/4/8 Bytes, Float, Double; decimal/hex/signed formatting, validated writes, readback and freeze |
| Special values | Exact bounded byte arrays, inherited zero-length array headings, and bitfields with fresh masked read/modify/write under an OS-held data event; disjoint freezes coalesce |
| String values | Bounded ASCII/UTF-16LE, exact fixed spans or prefix plus terminator, preserved remote tail, coordinated writes/Freeze and no saved value replay; codepage inputs remain blocked |
| Addresses | Nested brackets, arithmetic, `$process`, module/export atoms and inherited parent addresses; flattened XML pointer offsets |
| Signed pointer offsets | `<Offsets>` literals accept an explicit sign (`+28` = `0x28`, `+0x130`, `-0x10`); malformed sign forms (`++10`, `+`, `0x`, empty, trailing junk) are rejected fail-closed (WP-14) |
| Staged capability | Supported records whose address needs a symbol uniquely provided by another supported record carry `staged` provider metadata; the engine gates read/write/freeze on provider liveness (named fail-closed error while inactive, UI pending state with auto-unlock); provider OFF releases frozen staged children before deactivating (WP-14) |
| Script-parent cascades | The tested flag-class contract extends from group headings to script records with children (`required_dependency` / `direct_activation` / `collective_off`); ON activates the provider script before its children, OFF releases staged-child freezes first; `moBindActivation` on non-heading parents and value parents with flags stay visible named blocks (WP-14) |
| Record-ID activation sets | The converter statically extracts `getMemoryRecordByID(<int>)` + `Active = true|false` sets from embedded `{$lua}` (uniform direction per section, all IDs must exist); plan entries carry `activation_sets`; enable/disable applies the set through the engine's dependency-ordered activation instead of executing the CE-coupled Lua; both plan validators re-derive and refuse tampered metadata (WP-14) |
| Assembler grammar | ENABLE/DISABLE, distinct bounded process/module/range AOB scans, compact byte/nibble wildcard patterns, definitions, labels/anonymous labels, alloc, align, typed data, readmem, reassemble and symbol lists/scoped cleanup |
| Encoding/linking | NASM at actual target addresses, x86/x64 including SSE/AVX; iced displacement validation and relocation |
| Instruction literals | One printable ASCII character encodes as its integer immediate; source identity remains unchanged, with no implicit target API resolution |
| Remote imports | Bounded remote PE export/forwarder resolution for the target architecture; no local DLL address substitution |
| Hook lifecycle | Near allocation, RW staging, RX code with proven memory effects / RW data / RWX mixed or conservatively writable code, cache flush, guarded publication, exact restoration and durable receipts |
| Thread coordination | Dedicated Windows debug-event owner; held OS event and every observed thread IP outside overwrite ranges; competing debugger and displaced CALL/interrupt refusal |
| Retirement | Published code retained through disable until the exact PID/creation-time target exits; bounded target-lifetime allocation budget |
| Lua language | Upstream Lua 5.3 with 64-bit integers, memory quota, finite execution slices, cancellation and protected-call budget propagation |
| Lua host profile | Address/module/typed memory, strings, bytes, MemoryRecord lookup/value/Active, scan list wrappers, exact byte-array MemScan/FoundList, serialized timers, owned cooperative workers/sleep/cancellation, keyboard/controller reads and explicit phase-selected returned AA |
| Mutation ownership | Record writes use the controller; raw Lua writes/symbols/autoAssemble require supplied activation-owned brokers |
| Automatic Lua records | Original source/phase hashes, private helpers, bounded explicit/phase/EOF Lua sections, common-preamble scope, `luaCall`, owned data undo, returned-AA inverse, scoped receipts and cancellation |
| Nth AOB helper | Complete literal module/occurrence calls with an independent reserved helper or exact reviewed input-helper provenance; bounded ascending matches, captured owned scan symbols, actual dry link and held-publication context recheck; disable never rescans |
| Executable provider flags | Source-proven `db/dw/dd/dq` literal spans with live opaque provider permits; coordinated full-span numeric and masked bit-field writes/freezes under single-permit full coverage; bit-field spans not fully covered by one live permit and mixed ordinary/executable batches remain blocked (named refusals) |
| External literal data | Source-reconstructed pure literal AA entries receive opaque live exact-RW permits, use held data events, restore captured bytes and end terminally; mixed executable/external data remains blocked |
| Shared globals | Source-bound literal RW storage with original scan captures, private live consumer leases and exact compatible initializer reuse; published storage remains until target exit, live close quarantines controller restart; readmem/code initializers and strict recovery remain open |
| Work accounting | Separate Lua/transport, trusted broker and cleanup allowances; one controller-owned Restoration ledger bounds nested rollback/reclamation (30 s, 65,536 mutations, 128 MiB). Mandatory in-flight protection/cache repairs may finish after expiry; no hard Win32/fsync preemption or whole-close time limit |
| Typed calls foundation | Owned preloaded x86/x64 DLL and fixed compiled signatures, versioned bounded pipe, exact identity/deadline/nonce and one-shot completion; source-only, no engine/game/managed installation |
| Recovery | Source CLI assessment and explicit dead-owner/dead-target recovery; exact FILETIME identities, immutable file evidence, held-file archive/readback and durable recovery fence |
| Clock foundation | Independent integer scaling/epochs/leases and local v2 wrapper deadline/generation protocol, tested x64/x86; no installed speedhack claim |
| Target architecture | Explicit source/selection/identity-bound x86/x64 plan, early mismatch refusal, AMD64 host proof, PE-checked WOW64 duplicate handling; frozen owned x86 gate passed |
| Trainer/converter | Independent Tk UI (compact touch-first row grid: one row per record with pill toggle, inline value editor, collapsible group sections with counters, 48–64 px rows, 2×3 chip fallback under 650 px width); selected provider closure, source JSON and checked-template EXE generation, confirmed saved switches |

Static inspection never executes table Lua. Original table Lua is replayed only
as private helpers for an owned Lua record activation, under a sticky read-only
broker/scheduler gate. Top-level writes, callbacks, custom-type registrations and
unknown APIs visibly refuse activation. Shared table globals and original forms
are not yet reproduced. Returned AA is linked at actual addresses and must describe
the captured inverse; a failed enable compensates owned changes before saving an
ON wish. Public symbolic scan-option/rounding names are
profile tokens; numeric value-type constants use the published API values. The
scan profile currently supports exact byte arrays, not every CE scan mode.

## Coverage and evidence

The current 30-table synthetic corpus measures **6,143 expected actions**
(records minus navigation; 1,291 groups counted separately) per
`gap_inventory/gap-report.json`. The feature matrix covers 42/42 in-scope
features (7,475/7,475 action-weighted), but the full real reference corpus is
not fully supported: the local-only static catalog has 2,698 of 117,624 plan entries blocked. AP-11 has 0 confirmed real-game actions and runtime acceptance remains
`runtime_unverified: true`. Per-record and per-gap detail is in
[native-semantic-denominator.md](native-semantic-denominator.md). Static
admission and synthetic linking do not demonstrate game behavior. The October
11, 2026 figures (14 tables / 6,011 actions) are historical.
The new candidate is the promotional Lua dialog/browser record of
case-10 (origin: Senua's Saga Hellblade 2) after EOF acceptance; it has
no confirmed native GUI/browser API or cheat effect.

Owned C fixture tests demonstrate CT-to-engine executable hooks, confirmed saved
activation and disable, real Lua record writes with independent memory readback,
near allocation, remote exports, and retirement after a cave is still in flight.
Concurrent x64 and WOW64 fixtures exercise repeated debugger-held hook changes,
thread churn, debugger conflicts, lease expiration, handle stability and target
exit. Frozen executable/source-export evidence is recorded separately in
[`native-verification.md`](native-verification.md).

## Limits that remain part of the goal

The debugger proves physical quiescence for bounded changed ranges. Saved exception
contexts and unknown future branches into instruction interiors remain unverified.
Attaching is debugger-visible and may be rejected by a target. No privilege or
existing-debugger conflict is bypassed. Code/data allocation mode is explicit;
mutable flags inside mixed executable allocations use coordinated, source-proven
literal spans for child scripts. General masked writes to executable data remain
blocked. Never infer game acceptance from the
simple pure-code fixture.

Mutation uncertainty blocks subsequent writes and retains evidence. A prior
unfinalized allocation receipt blocks a new controller. Explicit source CLI
recovery now archives and releases exact stale file objects only after proving
both owner and all recorded target identities dead; legacy/unknown/live cases
remain blocked. Recovery is not yet exposed by the frozen converter/trainer UI.
Executable literal patches also use durable hook transactions; numeric writes and
freezes require live literal provenance on executable pages. Mixed executable/external-data literal scripts
remain refused before publication, pending a combined held-proof contract. Unknown syntax or ownership remains a visible block.

Lua is a restricted embedding profile, not an operating-system sandbox. The
controller owns target identity and generation. Timers are serialized and cancelled
on detach. Syntax checks use disposable Lua states and replay private helper
definitions; checker globals cannot leak into active records. Lua allocator quotas
and aggregate Python transport work budgets are separate. Owned cooperative
workers/coroutines cancel with their activation; arbitrary host threads/processes
and target-native threads remain outside that profile. General custom types,
table-load lifecycle/forms, original async/parent propagation and remote speed
control remain subsystems to implement and test. Broad automatic
case-06 (origin: Resident Evil 2) support is not claimed.
Game builds, a clean second PC, touch/DPI and Steam Deck/Proton remain acceptance
requirements.

## Build and use

Use Windows x64 Python 3.12 for the pinned runtime wheels. The full checkout builds
offline without accessing CE inputs:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/Build-Native.ps1
```

Each run receives a fresh `build/runs/native-<ID>/`, input checks, explicit
`suite-tests.log`/`.json` with tested source hashes, converter
and trainer template, archive inventory, source ZIP and portable ZIP. Existing
release archives are preserved. The converter embeds the checked template; a
trainer appends hash-bound declarative data and needs no separate Python, NASM,
Lua or CE installation.

The source CLI has explicit recovery commands. Assessment performs no mutation;
recovery first verifies and archives the exact evidence, then releases held stale
file objects while retaining committed desired state. A new trainer must still
attach to a freshly verified target before applying saved switches:

```powershell
python -m ct2trainer.native assess-recovery plan.json --state-dir <state> --process-lock-dir <shared>
python -m ct2trainer.native recover plan.json --state-dir <state> --process-lock-dir <shared> --archive-dir <fresh-evidence>
```

```powershell
$env:PYTHONPATH='src'
python -m ct2trainer.native inspect tests/windows/hook_fixture/hook_trainer.ct --process NativeHookFixture.exe
python -m ct2trainer.native build tests/windows/hook_fixture/hook_trainer.ct --process NativeHookFixture.exe --template <run>/bin/CT2Trainer-Template.exe --output HookTrainer.exe
```

The source ZIP includes pinned native archives. Restore NASM with
`tools/native_build.py restore-nasm --output .tools/native-tools`, set
`CT2TRAINER_NASM` to its absolute executable path, install the two archived
runtime wheels and run the Native suite. Its README gives the source build command.
The full-checkout offline script additionally uses the archived Python/PyInstaller
inputs; these larger build dependencies are excluded from the source ZIP.
