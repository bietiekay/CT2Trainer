# Reference-table 100% roadmap

Status: 2026-10-20. Active plan after the 0.16 Wave 4 release. The older
AP/WP plans record completed implementation history; this document defines
the next work. [TRACKING.md](TRACKING.md) is the status ledger.

## Outcome and measurement

The target is **all 151 local-only reference-table paths, including all 143
distinct byte hashes, supported for their intended behavior** by an
independently implemented, redistributable CT2Trainer. The snapshot is fixed
by a manifest of path, SHA-256, format, and exact target EXE name. Replacing
or adding a table creates a new baseline; it does not silently change the
denominator. Preserve original tables outside Git and release archives.
The requested parity scope is trainer/cheat handling and game-facing
effects. CE's editor and visual UI do not need replication. A UI API used
by a table to cause a game-facing effect must still have an equivalent
behavioral path; a purely decorative UI call can be classified no-effect.
The initial [capability assessment](../documentation/ce-feature-parity-assessment.md)
defines this scope and the evidence method.

"Supported" has three separate proofs:

1. **Load and inspect:** every table is read. Every source record and
   game-facing table-level construct is accounted for; UI-only constructs
   are classified separately.
2. **Plan and execute:** every intended actionable record can be built and
   exercised with the right dependency, activation, disable, value, resource,
   and UI behavior. A `staged` record counts only after its runtime gate is
   exercised. A named blocked record is honest but does not count as
   supported. Inert headings and malformed/no-effect rows are classified
   separately with evidence, never used to inflate the action numerator.
3. **Observed effect:** for each original table, representative actions and
   every distinct behavior contract are verified against the intended game
   build or an explicitly equivalent owned target. Static compilation and
   synthetic fixtures alone do not prove the original game effect. Windows
   and Steam Deck acceptance remain separate.

The existing 42/42 feature matrix covers the **30 synthetic pinned cases**;
it is not a 100% result for the original reference corpus. The current
original-table catalog is **114,926 supported (58,950 staged) and 2,698
blocked out of 117,624 plan entries**, with one whole-table legacy-binary
read error, from the 2026-10-20 post-Wave-4 run. The AP-11 synthetic
campaign has **0/6,143 confirmed game effects**. These are separate metrics.
The 151 paths include duplicate bytes; report both path and distinct-hash
coverage. Re-run the catalog on the exact 0.16 source with a fixed process
manifest before changing code, since the catalog is local-only evidence.

Progress reports must state the numerator/denominator for table load,
actionable records, staged runtime validations, observed game contracts,
Windows, and Deck. Do not call the overall goal complete until each is full
and every exception has a documented, user-approved scope decision. A
legacy binary table, missing source asset, or deliberately unsupported CE
host API is a remaining gap under this goal, even if its refusal is safe.

## Clean-room boundary

The CE 7.5 local source tree may be read solely to identify behavior and
public format/API contracts under the user decision in `AGENTS.md`. No CE
code, binary, table content, or derived implementation enters CT2Trainer.
Write original designs and synthetic minimal cases; record the behavioral
observation and independent implementation separately. The converter and
local analysis never execute original-table Lua or AA. Runtime execution
is confined to a generated trainer attached to its intended target. Keep
the original reference corpus and raw catalogs local-only.

## Ordered work

| ID | Deliverable | Acceptance |
| --- | --- | --- |
| RT-1 | Reproducible full-corpus baseline | Versioned local manifest for 151 paths/143 hashes; exact process bindings; same-source catalog; per-table and per-reason counts; record IDs and provider chains; 0.16 comparison with no unaccounted regression. Separate parse errors, inert records, staged rows, actionable rows, and table-level constructs. |
| RT-2 | Root-cause map for every residual | Resolve all 2,698 blocked entries to an upstream cause or verified malformed authoring input. Follow provider cascades to their root; distinguish real missing semantics from false positives and duplicate provider policy. Record a testable contract, risk, and expected delta for each class. |
| RT-3 | Load all table formats | Investigate the remaining legacy binary CT format with a clean-room parser or documented conversion path; preserve record identity and data. Table load reaches 151/151, subject to explicit evidence for genuinely unreadable inputs. |
| RT-4 | Close high-volume plan gaps | Execute the RT-2 root-cause-map packages in suggested order by expected delta over risk: P1 duplicate-provider/duplicate-label policy 814, P2 hidden in-table registration cascades 963, P4 relative-address base propagation 341, P3 Lua runtime symbol providers + no-registration triage + Lua-only enables 203, P5 legacy built-ins + API exports 140, P6 AA expression/directive grammar & format tolerance 122, P8 value/display semantics 64, P7 AA ownership/cleanup envelope & table-level constructs 43, documented refusals 8 — the split sums to 2,698. Each package: leading-table inspection, an independently authored synthetic case, the class contract as a testable assertion, owned-target runtime tests where effects matter, full suite, catalog delta with zero unexplained supported regressions, and a remeasure. A reason count is not an independent feature count; remeasure after each fix. |
| RT-5 | Runtime trainer parity | Inventory every used CE Lua/AA API and game-facing table-level construct, including dynamic records, callbacks, target threads, managed resolution, string hex view, and byte-width dropdown semantics. Implement each needed behavior with bounded contracts, teardown rules, and owned-target tests; classify purely visual UI as outside scope. |
| RT-6 | Full original-table validation | For each path, produce a plan-inspection result and targeted runtime observations against a pinned game build where available. Record skipped or inaccessible targets honestly. Run the Windows clean-machine and Deck/Proton/touch protocols; keep `runtime_unverified` until both pass. |
| RT-7 | Release gate | Rebuild only through `scripts/Build-Native.ps1`; full suite and source/frozen parity; `ce_inputs: []`; archive hashes and provenance; update tracker, ledger, and verification before declaring 100%. |

RT-1 and RT-2 are the first implementation cycle. RT-3 and RT-4 follow
root-cause evidence; RT-5 can proceed in isolated files after contracts
are specified. RT-6 runs continuously as target access permits. There is
no percentage shortcut based on the old feature matrix or an estimated
closure rate.

## Immediate investigation queue

Update (2026-10-21, RT-1): the re-run on the 0.16 source (frozen manifest
`gap_inventory/reference-manifest.json` committed, catalog
`blocked-catalog-rt1`) reproduces the 2026-10-20 counts exactly per table
(2,698 / 117,624, 1 legacy-binary load error).

Update (2026-10-21, RT-2): every one of the 2,698 blocked rows is now
traced to an upstream terminal cause (lane attribution run, final
classification `rt2_final2`; the root integrator re-verified every class
sum and per-table sum in both directions and independently re-ran the
corrected UNDEFINED-split logic against the local corpus). The
2026-10-20 queue's leading reason occurrences decompose exactly into
the classes below: `Esau_base` (600) = duplicate-provider cascades,
`mouse_ovr` (84) + `loot_ptr` (62) = hidden in-table registration
cascades in the Witcher3 pair, `BaseAddress` (80) = legacy built-ins,
pointer offsets (53) = direct hex-literal refusals. The queue's rule to
inspect the actual local table shape, reproduce the leading case with an
independently authored synthetic table, and specify the expected runtime
behavior before any code package still governs RT-4 (integration
protocol below). The Wave-4 snapshot's one known load error,
`SuperMeatBoy.CT` (legacy binary format), is RT-3 scope and is not part
of the 2,698.

### RT-2 root-cause map (2,698 rows, final2 run 2026-10-21)

Decomposition: **2,698 = 1,931 provider-cascade rows + 767 direct
rows.** Cascade terminals: **1,304 undefined-symbol rows** (963
AA_HIDDEN + 110 LUA_RUNTIME + 91 NO_REG + 128 LEGACY_SYM + 12
API_EXPORT) + **624 duplicate-provider cascades** + **3 wildcard-cleanup
conflicts**. A first-matching catalog reason can hide the terminal
cause; the map records the terminal class, not the first reason.

**Cascade classes (1,931 rows):**

| Class | Rows | Top tables (rows) | Upstream root cause | Classification | Testable contract | Risk | Expected delta | Pkg |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AA_HIDDEN | 963 | DSDC 121+120, re2_testicles 114, DS2 110, HFWest 63+63, Witcher3 89+87, Subnautica 32, LADG 26, ctts 25 | required symbol is registered in-table (registersymbol incl. multi-name, label(), bare `sym:`) but the static analyzer misses the registration; the first-matching reason hides it | analyzer false positive (registration resolution) | every in-table AA registration resolves: a synthetic table registering S via each registration form and then referencing S compiles with 0 blocked rows | high (multi-block/multi-name/case handling; must not mask true gaps) | up to 963 (residual = genuinely missing registrations) | P2 |
| LUA_RUNTIME | 110 | HFWest 39+39, DS2 30, RiftApart 2 (g_GameModule, g_GameState, Trampolines, g_DSPlayerSystem, ...) | symbol is provided at runtime by the table's own embedded Lua `registerSymbol`; invisible to the static compiler | runtime-provided symbol (static false positive) | symbols registered via Lua `registerSymbol` in the same table are accepted as providers in the static plan; resolution defers to the staged runtime; a missing registration fails at runtime with a named error | medium (runtime resolution must stay fail-closed; no static address baking) | up to 110 | P3 |
| NO_REG | 91 | GoW 32 (goPlayer/goGameObject), DS2 28 (InteractionPad/g_DebugSettings/g_Viewport), 小猫咪大城市 14 (CatValues), RiftApart 5, YLIL 3, HFWest 3+3 | no static registration evidence anywhere (no AA, no Lua): runtime host/user-provided or a genuine authoring gap | mixed - per-symbol triage (runtime provider vs authoring gap) | a symbol with no in-table registration blocks with the terminal cause named; it compiles only once registered or an approved runtime provider supplies it; a synthetic case proves both the blocked and the resolved path | medium (~30 distinct symbols; some need runtime-provider contracts) | up to 91 (ceiling; authoring residuals stay documented) | P3 |
| LEGACY_SYM | 128 | HellPie 18, AtomicHeart v1.2 17, Oregon 17, Scorn 17, Callisto 17, F4 9, LikeaDragonIshin 8+7, SOTTR 3, +13 | CE legacy built-ins/keywords (BaseAddress across the five UE5 template tables, Inf, assembly mnemonics/keywords such as st/int/end/dqword/float, table-local bases pbase/ctts/likeadragonishin/pgengine) that CT2Trainer does not define or misreads as symbols | missing legacy built-ins + keyword false positives | BaseAddress resolves to the attached main-module base; Inf resolves per CE 7.5 semantics; assembly keywords/mnemonics are never treated as symbol references; table-local bases resolve when registered in-table (else NO_REG); tests: a synthetic BaseAddress table compiles, and programs containing `int 3`-style mnemonics create no symbol requirement | low per built-in; medium for the keyword fix (parser change) | up to 128 | P5 |
| API_EXPORT | 12 | ForgottonAnne 2, SOTTR 2, trine2 2, +6 (FindWindowA/FindWindow, GetAsyncKeyState) | terminal symbol is a Win32 API export, never registered in-table; CE resolves it at attach | real missing semantics (runtime API export resolution) | API export names resolve at attach via OS lookup; unresolvable gives a named block reason; static plan marks them runtime-resolvable; test: FindWindowA resolves on the fixture target | low-medium (runtime-only; fail-closed when the target lacks the export) | up to 12 | P5 |
| DUPPROV_CASCADE | 624 | five shared UE5 template tables x 120 character_pointer (600), remainder spread | the provider cascade terminates at a duplicate provider registration: CE keeps the first registration (dupIgnore) and shadows later ones; CT2Trainer fail-closes the cascade | duplicate-provider policy (parity divergence) | duplicate provider registration keeps the first registration; dependents resolve against the kept provider; no blocked row arises from duplication alone; test: a synthetic table registering the same symbol twice compiles, kept provider = first | low-medium (kept-first must match author intent in the top tables) | up to 624 | P1 |
| WILDCARD_ROOT | 3 | Octopath2 3 | the cascade terminates at the wildcard-cleanup + externally-owned-symbol (mem0x04) conflict | ownership model (same family as CLEANUP_OWNED / WILDCARD_CLEANUP) | the ownership decision of P7 | medium | up to 3 | P7 |

**Direct classes (767 rows):**

| Class | Rows | Top tables (rows) | Root cause | Classification | Testable contract | Risk | Expected delta | Pkg |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| RELADDR_SKIP | 331 | Octopath2 327, +4 | relative offset applied over an addressless script/value ancestor; no base to propagate | real missing semantics (base propagation through script/value nodes) | pointer chains with a script/value ancestor resolve the base at runtime; the static plan records the dependency; an ancestor that can never carry an address blocks with this named reason; synthetic chain blocks before, resolves after | high (runtime base tracking) | up to 331 | P4 |
| DUPPROV_POLICY | 186 | SOTTR 38, Borderlands3-V10 14, ForgottonAnne 11, qt-ds-1/2 9+9, APlagueTaleInnocence 7, +88 rows across the remaining tables | direct duplicate provider registration (kept provider, later registration would shadow) | duplicate-provider policy (parity divergence) | same contract as DUPPROV_CASCADE | low-medium | up to 186 | P1 |
| PTR_OFFSET_HEX | 53 | CP77 30, Callisto V1.1 9, working.ct 9, SOTTR 3, HFWest 1+1 | pointer offset written as a non-hex literal; grammar requires a hex literal | format tolerance gap | pointer offsets accept decimal integer literals (parity; same plan as the hex equivalent) or stay a documented refusal; decision recorded with the CE check | low | up to 53 | P6 |
| TRAILING_TOKENS | 43 | DS2 10, GingaForce 8, Subnautica 6, PennysBigBreakaway 3, REZ 3, YLIL(1) 3, +10 rows across the remaining tables | address expression carries tokens the parser rejects: define(bytes,/define(address, directives with byte-string args, digit-leading labels (0CurrentWeight:), method atoms with trailing tokens (TechData:get_craftAmount+b), trailing space in quoted atom | parser tolerance (per-case verification) | the AA expression grammar accepts the token forms used by the reference corpus, verified per case; unsupported forms block with a line-specific named reason | medium (grammar expansion surface) | up to 43 | P6 |
| CLEANUP_OWNED | 31 | DS2 13, re2_testicles 3, ctts 2, Starfield 2, trine2 2, Cronos 1, +8 rows across the remaining tables | cleanup releases symbols/allocations not owned by this program (cross-block ownership) | ownership model (policy decision) | cleanup may only release symbols/allocations allocated by the same program; cross-block cleanup is supported via shared ownership or blocks with a named reason (decision recorded) | medium (memory safety on disable) | up to 31 | P7 |
| DROPDOWN_WIDTH | 30 | P3R v4/v5/v1 9+9+9, P3Reload v1.5.1 3 | dropdown choice exceeds the value-type width ('314' over Byte) | parity divergence: CE truncates, CT2Trainer refuses | write the low N bits (truncation) to match CE (CE probe a below); test: a Byte dropdown choice 314 writes 58 | low (matches CE) | 30 (full) | P8 |
| STRING_SHOWASHEX | 15 | DS2 9, HFWest 3+3 | string entry uses the ShowAsHex byte view; CT2Trainer requires literal text display | display/view feature - no game-facing effect (string content unchanged) | string entries with ShowAsHex compile with literal-text display; the hex byte view is classified decorative/no-effect (rows reclassified, not code-fixed) - or the byte view is implemented | low | up to 15 (reclassification) | P8/scope |
| DROPDOWN_EXPR | 13 | Borderlands3-V10 12, P4G 1 | dropdown choices are unsupported value expressions (IL2CPP Type:Member atoms) | runtime symbol resolution (IL2CPP; CE probe c below) | choices referencing Type:Member resolve at runtime via the IL2CPP pipe; the staged gate fails closed when the backend is absent | medium-high (needs the IL2CPP runtime; RT-5) | up to 13 | P8 |
| RELADDR_NO_ANC | 10 | SOTTR 10 | relative address with no address-bearing ancestor at all | real missing semantics (same family as RELADDR_SKIP) | same contract as RELADDR_SKIP | high | up to 10 | P4 |
| SYM_CHARS | 8 | recolored 5, Octopath1 2, RDR2 1 | symbol names start with a digit (8PathBattleResult) or contain non-ASCII characters; CT2Trainer restricts to [A-Za-z0-9_] | parity gap (charset policy) | the symbol charset widens to CE 7.5's accepted set with a deterministic internal encoding; test: a non-ASCII symbol and a digit-leading symbol round-trip through the plan | medium (encoding round-trip) | up to 8 | P6 |
| CUSTOM_TYPE | 6 | re2 3, re2_testicles 3 | custom value types (RE2_Hrs/Mins/Secs) have no static definition; need a converter/write gate (AP-08.7) | real missing semantics (custom type runtime) | custom types with converter scripts resolve at runtime; the static plan records the type; writes go through the converter gate; test: an RE2_Hrs value write via the converter | medium | up to 6 | P8 |
| INDIRECT_DATA | 5 | SandFall V1..V5 1 each | indirect address expressions in the data dialect (aobAppendString+7+(DWORD)[aobAppendString+3]) | real missing semantics (data-dialect indirection/cast) | data expressions support casted indirection (TYPE)[expr]; test: a synthetic aob+cast+deref plan is byte-identical | medium | up to 5 | P6 |
| AOBSCANREGION | 5 | Subnautica_e67616 5 | unsupported AA directive aobscanregion (secondary: dealloc size outside 1..1048576) | missing AA directive support | aobscanregion (range-bound AOB scan) is implemented or a documented refusal with a named reason | medium | up to 5 | P6 |
| LUA_C_DIRECTIVE | 4 | Borderlands3-V10 4 | embedded Lua/C/compiler-preprocessor directives inside record AA (line 17) with a trailing-token artifact | unsupported directive (scope decision) | the directive family is supported or blocks with a named reason (decision recorded); the reason must not degrade into a generic trailing-token artifact | low | 0-4 | P6/scope |
| MALFORMED_DIRECTIVE | 4 | ForgottonAnne 2 (usemono), 小猫咪大城市 2 | usemono/.NET AA directive + malformed directive arguments | scope decision (mono AA out of scope) or authoring gap | mono AA stays a documented named refusal unless a user decision changes it; test: the refusal reason is stable | none (documented refusal) | 0 | scope |
| DUP_LABEL | 4 | re2 1, re2_testicles 1, Witcher3 1+1 | duplicate label/program symbol (dCusWetAmount; duplicate return label); CE tolerates via dupIgnore | duplicate-symbol policy (parity) | duplicate label/symbol registration is tolerated per CE 7.5 dupIgnore semantics (kept per CE source); no hard block; test: a duplicate-label table compiles | low | up to 4 | P1 |
| ALLOC_CLEANUP | 3 | AtomicHeart 1, P3R-v4 1, Shinkansen 1 | unsupported AA directive alloc outside the supported envelope (secondary: unbalanced args / reassemble arg count / ':get_Level' expression) | missing AA directive support (+ possible authoring malformation) | alloc/dealloc are accepted within the supported size range; out-of-range/unbalanced blocks with a named reason; per-sub-case tests | medium | up to 3 | P6 |
| WILDCARD_CLEANUP | 3 | Octopath2 3 | wildcard cleanup combined with an externally owned symbol (mem0x04) | ownership model (same family as CLEANUP_OWNED) | same contract/decision as CLEANUP_OWNED | medium | up to 3 | P7 |
| GLOBAL_INIT | 2 | Resonance 1, SinkingCity_Rem 1 | global initializer requires one direct ENABLE cursor; the table uses another structure | real missing semantics (global init structure) | global initializers with a non-single-cursor structure are supported or a documented refusal (decision recorded) | medium | up to 2 | P7 |
| NO_EXEC_PATCH | 2 | SOTTR 2 | enable section contains only a Lua call (luaCall(lua_aobscan(...))); CE executes record Lua at activation time | runtime Lua activation semantics (RT-5) | Lua-only enable sections are accepted by the static plan and executed by the record-Lua path at activation; test: a synthetic lua-only enable activates on the fixture target | medium (depends on record-Lua lifecycle) | up to 2 | P3/RT-5 |
| GLOBAL_INIT_LABEL | 2 | SinkingCity_Rem 2 | labels inside a global initializer are outside the direct literal profile | same family as GLOBAL_INIT | same contract as GLOBAL_INIT | medium | up to 2 | P7 |
| CREATETHREAD | 2 | Witcher3 1+1 | createThread()/threadWait() are gated: no thread backend is part of the shipped trainer | missing runtime backend (RT-5) | createThread/threadWait resolve against the staged runtime thread backend; absent backend fails closed with a named gate; test: a synthetic thread program on the fixture target | medium-high (thread backend) | up to 2 | P7/RT-5 |
| QUOTED_ATOM | 1 | CP77 1 | quoted atom is not a module basename; CE module list stores names with the .exe extension (CE probe b below) so CE would not resolve it either | authoring gap (keep the refusal) | the refusal stays; the reason names the expected form; test: a quoted atom must match an attached module basename | none | 0 (documented) | scope |
| ASSERT_ARGS | 1 | CP77 1 | assert with an invalid argument count (malformed) | authoring gap | stays blocked with the named reason; a test pins the refusal | none | 0 | scope |
| BLOCK_COMMENT | 1 | SonicFrontiers 1 | unterminated source block comment | authoring gap | stays blocked with the named reason; a test pins the refusal | none | 0 | scope |
| OTHER | 1 | Sunless Skies 1 | invalid address expression near ':set_EffectiveLevelM' (method-call-style atom) | expression-grammar gap (triage per case) | named reason; decision: support the method syntax or document the refusal | low | 0-1 | P6 |
| DROPDOWN_EMPTY | 1 | 小猫咪大城市 1 | read-only dropdown has no concrete literal choices | authoring/scope | stays blocked with the named reason or is classified no-effect after review | none | 0-1 | scope |

Class total check: 963+110+91+128+12+624+3 + 331+186+53+43+31+30+15+13+10+8+6+5+5+4+4+4+3+3+2+2+2+2+1+1+1+1+1 = 2,698.

### RT-4 package split (sums to 2,698)

| Package | Scope | Rows |
| --- | --- | --- |
| P1 | duplicate-provider & duplicate-label policy (DUPPROV_CASCADE 624 + DUPPROV_POLICY 186 + DUP_LABEL 4) | 814 |
| P2 | hidden in-table registration cascades - analyzer registration resolution (AA_HIDDEN) | 963 |
| P3 | Lua runtime symbol providers + no-registration triage (LUA_RUNTIME 110 + NO_REG 91 + NO_EXEC_PATCH 2) | 203 |
| P4 | relative-address base propagation (RELADDR_SKIP 331 + RELADDR_NO_ANC 10) | 341 |
| P5 | legacy built-in symbols + API exports (LEGACY_SYM 128 + API_EXPORT 12) | 140 |
| P6 | AA expression/directive grammar & format tolerance (PTR_OFFSET_HEX 53 + TRAILING_TOKENS 43 + SYM_CHARS 8 + INDIRECT_DATA 5 + AOBSCANREGION 5 + ALLOC_CLEANUP 3 + LUA_C_DIRECTIVE 4 + OTHER 1) | 122 |
| P7 | AA ownership/cleanup envelope & table-level constructs (CLEANUP_OWNED 31 + WILDCARD_CLEANUP 3 + GLOBAL_INIT 2 + GLOBAL_INIT_LABEL 2 + CREATETHREAD 2 + WILDCARD_ROOT 3) | 43 |
| P8 | value/display semantics (DROPDOWN_WIDTH 30 + STRING_SHOWASHEX 15 + DROPDOWN_EXPR 13 + CUSTOM_TYPE 6) | 64 |
| documented refusals | authoring/scope gaps, no code fix (MALFORMED_DIRECTIVE 4 + QUOTED_ATOM 1 + ASSERT_ARGS 1 + BLOCK_COMMENT 1 + DROPDOWN_EMPTY 1) | 8 |
| **total** | | **2,698** |

Suggested execution order by expected delta over risk: P1, P2, P4, P3,
P5, P6, P8, P7 (43 rows), documented refusals 8. Remeasure the catalog
after each package (roadmap rule).

### CE 7.5 behavior probes (read-only reference, 2026-10-21)

(a) **Dropdown value overflow - CE truncates.** `MemoryRecordUnit.pas:3500`
(`vtByte: pb^:=StrToQWordEx(currentValue)`, QWord stored into a pbyte ->
low byte); write flow `addresslist.pas:1167-1174` (picker -> value
string) -> `SetValue` :3200+ -> per-type store :3500-3503. Out-of-width
values are not refused.
(b) **Module references without .exe.** The module list is built from
`extractfilename` and stores names **with** the extension
(`symbolhandler.pas:5753`); `getmodulebyname` is an exact case-folded
match (`:4567-4586`); `aobscanmodule` falls back to the symbol lookup
and then raises (`autoassembler.pas:1111-1128`). A bare module base name
therefore does not resolve as a module - only via symbol registration.
(c) **IL2CPP Type:Member.** The IL2CPP_* commands exist only at the C
pipe-server level (`PipeServer.h:194-367`); zero Delphi/Lua-level
references in the 7.5 tree. No native static resolution; tables rely on
runtime Lua registerSymbol/pipe (RT-5).

### Caveats

- Counts are static-catalog facts, verified in both directions (class
  sums and per-table sums each total 2,698); "expected delta" is the
  ceiling if the class contract is implemented. Per-table residuals
  (authoring gaps) remain blocked by design.
- AA_HIDDEN rows may re-bucket into P3/P5 sub-classes as the analyzer
  gains registration resolution; NO_REG rows are per-symbol triage.
  Remeasure after each RT-4 package.
- The one legacy-binary load error (SuperMeatBoy.CT) is RT-3 scope and
  is excluded from the 2,698.

## Integration protocol

Use a new milestone working branch. Each integrated package includes a
focused synthetic case, runtime tests where effects matter, full suite,
catalog delta with zero unexplained supported regressions, updated
[`STATUS.md`](../STATUS.md), central tracker and ledger in the same change,
then normal merge and push to `main` under `AGENTS.md`.
Root owns the catalog and documentation. Subagent lanes follow
`documentation/subagent-lane-rules.md`; when the user directs a different
launch policy for a session, follow that instruction. Never infer game
effect from a green static catalog.
