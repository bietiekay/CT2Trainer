# CE trainer-behavior parity assessment

Status: 2026-10-20. Initial general assessment for the user's 151 local
reference-table paths and the CE 7.5 behavior reference. This is a
**capability map**, not a claim that every CE feature or original table has
been exercised. The active completion plan is
[`plans/reference-table-100-roadmap.md`](../plans/reference-table-100-roadmap.md).

## Scope

Assess CE features that can change a trainer's game-facing effect: table
loading, memory records, Auto Assembler (AA), Lua host calls, address and
symbol resolution, lifecycle, target interaction, and undo. CE's editor,
scanner interface, debugger interface, windows, forms, menus, dialogs,
visual layout, and table-authoring conveniences are outside the requested
UI scope **unless** a script uses them to trigger or calculate a game-facing
action. An ignored UI call may be equivalent for a no-effect record; it may
not be silently ignored when it carries a target action or state dependency.

CE 7.5 at `C:\Users\xboxl\code\cheat-engine-7.5` is a local behavior
lookup only. The original tables at
`C:\Users\xboxl\code\reference-table-input-do-not-add-to-git` are
local-only inputs. No implementation code, binary or original-table body
may be copied or derived into CT2Trainer or its distributed archives.
Describe the contract, write an independent design, and pin an original
synthetic case.

## Current evidence

| Evidence plane | Result | What it proves |
| --- | --- | --- |
| Synthetic corpus | 30 pinned tables, 6,143 expected actions, 42/42 feature-matrix classes, 7,475/7,475 action weight | The declared synthetic matrix is covered; many actions remain statically classified as locked or assumed. |
| Original-table static catalog | 151 paths, 143 distinct hashes, 117,624 compiled plan entries: 114,926 supported including 58,950 staged, 2,698 blocked; one legacy-binary load error | A substantial but incomplete plan admission profile. First block reasons can hide downstream errors. |
| Runtime evidence | 0/6,143 AP-11 actions confirmed; Windows and Deck final gates open; `runtime_unverified` retained | No general original-game parity claim yet. |
| CE contract lookup | CE 7.5 local source and public CT/Lua/AA behavior, read-only | Can resolve ambiguities in behavior; does not authorize code reuse. |

The catalog's most frequent reasons on 2026-10-20 include `Esau_base`
provider (600 occurrences), relative address through an addressless
ancestor (331), `mouse_ovr` (84), `BaseAddress` (80), `loot_ptr` (62),
and pointer offsets (53). These are *reason occurrences*, not mutually
exclusive feature counts. The top blocked paths include Octopath Traveler
2 (333), DS2 (205), and Atomic Heart v1.2 (166). Reproduce on the exact
0.16 source and freeze the process bindings before assigning code changes.

## Capability map

"Implemented" means a bounded CT2Trainer path and tests exist, not CE
equivalence. "Partial" means a known subset or staged route. "Gap" means
an input can be blocked or its intended effect is not yet demonstrated.

| Trainer behavior family | Current assessment | Evidence and missing contract |
| --- | --- | --- |
| XML CT records, groups, values, dropdowns, hotkeys, assets metadata | Partial | Broad reader and runtime paths; still blocked offsets, byte-width choices and String `ShowAsHex`; duplicated IDs are tolerated. Legacy binary `SuperMeatBoy.CT` does not load. `table.py`, `compiler.py`, `value_types.py`, `hotkey_model.py`; catalog and `native-progress.md`. |
| Address expressions, pointer chains, dynamic parent addresses | Partial | WP-38/50 provide bounded dynamic bases; 331 addressless-ancestor blocks remain. A signed/decimal/hex expression may be handled differently at compiler and runtime. Trace each cascade to its provider. `address_expression.py`, `compiler.py`, `engine.py`. |
| AA grammar, patching, allocation, scans, symbol ownership and disable | Partial | Many patterns, staged scans, byte-exact undo and allocation-only programs are supported. Residual native-assembly syntax, cleanup/foreign ownership, and duplicate providers remain; `createThread`/`threadWait` has a model but the shipped default route remains gated without an owned backend. `aa.py`, `aa_program.py`, `aa_directives.py`, `engine.py`. |
| Lua record activation and table bootstrap | Partial | Record-scope host and table-lifetime bootstrap support defined subsets (including Wave-4 table timers/symbols). General CE Lua API, callbacks, mutable address-list records, arbitrary scheduler/thread behavior and unrecognized globals remain open. `lua_host.py`, `lua_activation.py`, `lua_bootstrap.py`; `runtime-parity-assessment.md` §4.1. |
| Runtime custom types | Gap for Lua-defined types | Static custom-type definitions have a bounded path; types registered through table Lua/AA such as the RE2 family are not generally available. `custom_types.py`; catalog and `reference-gap-assessment.md`. |
| Managed Mono/IL2CPP, target calls and speed control | Partial / validation gap | Bounded resolution/call/clock contracts and owned-fixture tests exist, but game-build resolution and effects are not generally confirmed. Treat source-to-frozen probe parity and fixture execution separately from original-game success. `native-runtime.md`, `native-verification.md`. |
| Target memory/process safety and persistence | Implemented bounded contract, acceptance open | Target identity, patch proof, compensation, detach, saved confirmed-ON wishes and recovery have tests. Clean-machine, debugger-conflict, real-game and Proton/touch evidence are still required. `engine.py`, `memory.py`, `native-verification.md`. |
| CE UI/editor/scanner as an application | Outside requested scope | Do not count absent visual/editor functions as trainer gaps unless they mediate target action. If an API is stubbed, prove that the stub preserves the table's game-facing behavior. |

The prior full-corpus frequency census in
[`runtime-parity-assessment.md`](runtime-parity-assessment.md#41-complementary-frequency-census-lane-r-runtime-parity-r-corpusmd)
identified record lifecycle callbacks (`onMemRecPostExecute`,
`disableWithoutExecute`, `onEnable`/`onDisable`), `synchronize`, and
dynamic record mutation (`createMemoryRecord`, `appendToEntry`, setters)
as large potential surfaces. Its counts are raw syntax occurrences and
may be inflated by duplicated tables or generated scripts. Recount by
distinct table hash and *game-facing use* before treating frequency as a
priority. Wave 4 completed several features that its 2026-10-18 list
then called missing, so its old status labels are historical.

## Reproducible general-assessment method

1. **Freeze inputs:** inventory all 151 paths with SHA-256, XML/binary
   format, target EXE name, game build if known, and duplicate-hash group.
   Keep manifest/raw evidence local-only; publish only aggregates and
   independently written synthetic cases.
2. **Extract feature usage without execution:** parse CT XML; walk every
   `CheatEntry`, AA ENABLE/DISABLE block, record Lua, table Lua, custom
   type, hotkey, resource and offset. Tokenize calls/directives with
   structure-aware parsing rather than a regex-only match. Record
   distinct hashes and record IDs for each feature. Never run table code
   during this pass.
3. **Build a CE contract inventory:** use the local CE 7.5 source only
   to answer specific behavior questions (arguments, ordering, lifetime,
   side effects, failure and undo). Reference file and symbol names in
   local notes. Do not translate or port CE algorithms or code.
4. **Map to CT2Trainer:** for every used contract, record implementation
   location, plan admission, frozen parity, runtime backend, tests, and
   known refusal. Mark `implemented`, `partial`, `gap`, `UI-only`, or
   `unknown`; "unknown" cannot count as covered.
5. **Trace cascades:** follow a blocked value to the provider and its
   first independent failure. A provider repair may unblock hundreds of
   rows; a generic `Required symbol` reason alone is not enough to
   assign a feature.
6. **Verify effects:** make minimal synthetic fixtures first, then
   exercise each distinct game-facing contract on an owned process and
   representative original table/game build. Record ON, value/freeze,
   re-attach and OFF/undo behavior; a one-shot gets its explicit
   no-OFF contract. Keep Windows and Deck results separate.
7. **Gate completion:** every original path loads; every intended
   action is executable and observed or has an explicit exception
   decision; no hidden staged/blocked records; all release and platform
   gates pass. Report path, distinct-hash, action and observed-contract
   denominators separately.

## First follow-up

RT-1 should generate the frozen input/usage manifest and reproduce the
2,698-block catalog. RT-2 should produce a root-cause table for every
residual, with special attention to the three leading blocked tables and
the provider/relative-address cascades. Only then split bounded
implementation packages. This assessment should be updated after each
catalog rerun, never inferred from the 42/42 synthetic matrix.
