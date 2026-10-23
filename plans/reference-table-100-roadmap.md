# Reference-table 100% roadmap

Status: 2026-10-23. Active plan after the 0.16 Wave 4 release; RT-3
(legacy-binary CT loading) and RT-4.4 (value semantics) landed 2026-10-23,
RT-4.1 (symbol provider fidelity) landed 2026-10-22. Catalog remeasure
`blocked-catalog-rt44`: 1,807 blocked of 117,634 plan entries, 151/151
tables load. The older AP/WP plans record completed implementation
history; this document defines the next work.
[TRACKING.md](TRACKING.md) is the status ledger.

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
| RT-3 | Load all table formats | Investigate the remaining legacy binary CT format with a clean-room parser or documented conversion path; preserve record identity and data. Table load reaches 151/151, subject to explicit evidence for genuinely unreadable inputs. — done 2026-10-23 (clean-room parser `src/ct2trainer/legacy_ct.py`; `SuperMeatBoy.CT` loads with all 10 records supported; run `blocked-catalog-rt3`). |
| RT-4 | Close high-volume plan gaps | Execute the RT-2 root-cause-map packages in suggested order by expected delta over risk: RT-4.1 symbol provider fidelity (dupIgnore policy, dup labels, wildcard-cleanup scoping) 820 — done 2026-10-22 (remeasured 2,698 -> 1,858 blocked), RT-4.3 address expression & identifier dialect 452, RT-4.4 value semantics 65, RT-4.5 AA directive & script coverage 57, RT-4.6 input legacy & authoring gaps 219, RT-4.2 runtime provider model 1,085 (last: its AA_HIDDEN portion clears progressively as root packages land). The split sums to 2,698. Each package: leading-table inspection, an independently authored synthetic case, the class contract as a testable assertion, owned-target runtime tests where effects matter, full suite, catalog delta with zero unexplained supported regressions, and a remeasure. A reason count is not an independent feature count; remeasure after each fix. |
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
traced to an upstream terminal cause (lane attribution, final
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
of the 2,698. The lane's final report (2026-10-21 21:14) is the
authoritative record: verified per-family roots for the AA_HIDDEN
family, all three open CE 7.5 probes closed, seven caveats; the map
below is the final report's per-class table (R1-R7 cascade, O1-O27
direct).

Update (2026-10-22, RT-4.1): the symbol provider fidelity package
landed (branch `native-rt4-1`, merged to `main` the same day). Three
clean-room code changes: (a) keep-first duplicate-provider policy in
`compiler.py::_dependencies` — a second entry registering an
already-registered symbol is no longer blocked wholesale; its duplicate
registration is shadowed (removed from the symbol's provider list) while
every non-duplicate registration in the same entry still takes effect;
first supported registration wins, matching CE `dupIgnore`
(autoassembler.pas:338/345 dedupes only the per-program disable-symbol
list; the AA runtime registration is delete-then-add,
autoassembler.pas:4164-4208, so CE is last-wins; keep-first is the
documented safe narrowing, `runtime-parity-assessment.md:257`);
(b) `aa_program.py::prepare_program` tolerates repeated names inside one
or more `label()` declarations (CE's duplicate-declaration check is
disabled at autoassembler.pas:2585-2586; multiple `name:` definitions,
2599, and never-defined names, 2603, are still refused; unresolved
label references still fail in the linker); (c) the wildcard-cleanup
static guard is removed — the wildcard sweep is scoped at runtime to the
program's own phase-owned symbols. Tests: nine focused modules 167 OK;
full suite 3,415 OK / 25 expected skips on `main` after the merge.
Catalog remeasure (local, run `blocked-catalog-rt41`, frozen manifest
and process bindings unchanged): **2,698 -> 1,858 blocked** (net -840;
117,624 total unchanged; staged 58,950 -> 59,642; the one legacy-binary
load error unchanged). 842 rows unblocked — all 624 R1
duplicate-provider cascades (600 `Esau_base` plus 24 non-template
cascade rows), all 3 R2 wildcard-cleanup rows, all 186 O2 direct
duplicate-provider rows, 2 of 4 O16 dup-label rows (re2 / re2_testicles
`dCusWetAmount`), and 47 R3 rows whose duplicate root cleared (LADG 26
`pbase`, AtomicHeart v1.2 21). Exactly 2 supported rows regressed,
both explained: Cyberpunk2077 ids 380/381 ("If Iconic Weapon / Item
Level 1/2") now refuse with "Required symbol has no unique supported
provider: weaponPtr" because keep-first leaves all three compatible
`globalalloc(weaponPtr,$32)` declarers (741/379/382) supported, so the
external value records are no longer ambiguously admitted — exactly the
pinned contract of
`test_native_global_engine::test_compatible_duplicate_declarers_share_
without_ambiguous_external_admission` (compatible shared-global
declarers share; external consumers are not admitted). In the baseline
they resolved only by accident: the duplicate providers had been
blocked earlier at the `weapon`/`weaponBkp` register-symbol duplicates,
which dropped them from the `weaponPtr` candidate set before the
shared-global check ran. Zero unexplained supported regressions. The
two Witcher3 O16 rows now compile past the `label()` duplicate but are
blocked at the next gate: `str_base` is a Lua-generated `define`
(`string.format("define(str_base, %X)", ...)`) the static compiler
cannot resolve — runtime-provider class (R3 root spans RT-4.2/4.5), not
a regression (both rows were already blocked). case-28 plan state
re-verified unchanged: 10 total / 9 supported / 9 actionable / 1
blocked, e[59] "Required symbol has no unique supported provider:
SynthOnly28" (pre-existing non-dup class).

Update (2026-10-23, RT-3): the legacy-binary CT format loads now
(branch `native-rt3` merged to `main` the same day). Clean-room parser
`src/ct2trainer/legacy_ct.py` (457 lines) reads the CE 5.x-era pre-XML
binary format: the true magic is 11 bytes (`CHEATENGINE\t` — the 12th
byte is the version-DWORD LSB, so the former 12-byte constant in
`table.py` matched only version-9 files by accident), format versions
6-9 are verified against the reference layout, version >9 loads with an
"assumed unchanged" warning, version <6 is refused as too old; truncation
(offset + remaining bytes), corrupt magic and implausible counts/lengths
carry bounded named `LegacyCTError` refusals (a `TableError` subclass,
so inspection diagnostics stay G4a). `read_table` dispatches
magic-matching files to the parser and everything else to the unchanged
XML path; the converted standard-XML document flows through the
unchanged, fully tested XML pipeline (`compile_table` consumes
`Table.converted_xml`), so record semantics, activation safety and
warnings are not re-derived. Source identity stays the original binary
bytes: `Table.source_sha256` and the plan `table_sha256` are the binary's
SHA-256 (matching the reference manifest), the converted XML is carried
on the unserialized `Table.converted_xml`. Record IDs are synthesized in
document order (top-level records in file order, then "Group N" headers
in numeric order with their members); pointer records keep the last
pointer's address plus the full offset chain (intermediate addresses are
not XML-expressible, documented); legacy code records become CheatCodes.
Tests: 28 new in `tests/test_native_legacy_ct.py` (byte-level parse,
conversion order/IDs/groups, pointer survival, CheatCodes blocks,
refusals, plan byte-stability, engine-level value write + AA roundtrip
on fixture memory) plus updated legacy pins in
`tests/test_native_table_robustness.py`; full suite on `main` after the
merge: 3,450 OK / 25 expected skips. Catalog remeasure (local, run
`blocked-catalog-rt3`, frozen manifest and process bindings unchanged):
**151/151 tables load** (the one legacy-binary load error is cleared),
total 117,624 -> 117,634, supported 115,766 -> 115,776 (all 10
`SuperMeatBoy.CT` records, 0 staged, 0 blocked), blocked unchanged at
1,858; the other 150 tables are byte-identical per-table — zero
regressions. `runtime_unverified` remains: the 10 AA records' real-game
effect is untested (standing gate).

Update (2026-10-23, RT-5): the inventory half of RT-5 is done —
`documentation/rt5-api-inventory.md` catalogs every used CE Lua/AA API
and game-facing table-level construct over the 151 reference tables
(394 distinct Lua call names: 61 CE globals, 36 CE object methods,
28 stdlib, 269 table-local; 20 CE globals hosted, 41 named-refusal gaps
split 14 game-facing vs 27 pure-UI no-effect; table-level construct
census with per-construct scope decisions). The implementation queue
(section 9 of the doc) is ordered after the RT-4 lanes: (A) embedded-
file extraction + `findTableFile`/`readStringLocal` (4 tables), (C)
bounded process-info APIs, (D) `onOpenProcess`/`onTableLoad` callback
dispatch (2 FearlessRev tables), (B) `CheatCodes` code-patch path
(22 tables, 175 entries), (E) `messageDialog` decision (31 tables),
(F) no-effect register ratification, (G) `createThread`/`threadWait`
backend decision (O22). Purely visual UI stays out of scope.

Update (2026-10-23, RT-4.4): the value-semantics package landed
(branch `native-rt4-4`, merged to `main` the same day). Clean-room
semantics per the CE 7.5 conclusions: (a) O6 DROPDOWN_WIDTH — CE
`SetValue` (MemoryRecordUnit.pas:3500-3503) parses choice strings with
`StrToQWordEx` and stores them through the typed pointer, truncating to
the record's byte width (choice '314' on a Byte writes low byte 0x3A =
58); `parse_value` now truncates every integer write to the record
width in both decimal and hex base modes (decimal mode: decimal regex
then hex fallback; hex mode stays hex-only, fail-closed) instead of
refusing at plan time; (b) O8 DROPDOWN_EXPR — bracketed choices on
simple-numeric records compile as `expression: True`, are validated by
`parse_expression` at plan time and resolved against the runtime symbol
table at write time (the bracket condition is strict: starts `[` and
ends `]`, length > 2 — CE SetValue 3449-3450 parity, so `[sym]+4` is
not an expression in either); alternate-base hex choice IDs on decimal
records are accepted as writable literals (deliberate documented
clean-room extension: CE's `StrToQWordEx` (parsers.pas:248) would route
bare hex-looking decimals through the float path and error there);
unparseable choices keep the refusal on writable records and become
display rows on read-only dropdowns; (c) O7 STRING_SHOWASHEX — string
records with ShowAsHex stage a `byte_array` value profile (hex byte
display; CE copies raw text on vtString — MemoryRecordUnit.pas
3534-3587 — so the byte-array staging is the documented clean-room
interpretation of the O7 row); (d) O26 DROPDOWN_EMPTY — read-only
dropdowns with empty or placeholder-only choice lists stage as
display-only views (the `*` placeholder drops out, possibly-empty
choices allowed) instead of refusing. The O11 custom-type gate is
unchanged by design (6 rows stay gated; refusal messages pinned in
`tests/test_native_compiler.py`). Plan metadata: `writable: False`
(display-only row) and `expression: True` (expression choice) markers,
enforced byte-identically by both plan validators (compiler
`validate_plan` and the engine wrapper). Tests: 18 new in
`tests/test_native_value_semantics.py` (byte-exact engine-level pins on
memory.data/memory.writes: signed wraparound '-1' on 4 Bytes ->
`ff ff ff ff` displayed 4294967295, '70000' on 2 Bytes -> `70 11`,
decimal '01E7' on 2 Bytes -> `e7 01`, hex-mode fail-closed, expression
pre-resolution before any write, read-only empty-set write refusal,
O7 byte-array roundtrip, O26 empty placeholder staging) plus pin
updates in `test_native_dropdown_separators`, `test_native_value_types`,
`test_native_compiler` and `test_native_engine` per lane-rules 6a. Full
suite on `main` after the merge: 3,471 OK / 25 expected skips. Catalog
remeasure (local, run `blocked-catalog-rt44`, frozen manifest and
process bindings unchanged): **1,858 -> 1,807 blocked** of 117,634
(net -51; supported 115,776 -> 115,827; staged 59,642 -> 59,683;
151/151 tables load, zero compile errors). Exactly 51 rows unblocked,
all in the expected classes: O6 30 (P3R/v4/v5 9 each, P3Reload 3),
O7 8 (DS2 2, HorizonForbiddenWest 3 + HorizonForbiddenWest (1) 3),
O8 13 (Borderlands3-V10 12, P4G 1). Zero newly blocked rows. Eight rows
change only their immediate block reason and stay blocked on the
pre-existing symbol-provider gate: DS2 25521/25524/25526 (ShowAsHex
string pointer records on the blocked `p` provider), DS2 87558/87561/
87563 (blocked `myPtr3`), DS2 87598 (blocked `myPtr2`) and 小猫咪，
大城市 id=3 (the empty-dropdown row now reaching the blocked `CatValues`
provider behind 小猫咪 id=2 `usemono`). No plan-level providers
involved; zero supported regressions.

### RT-2 root-cause map (2,698 rows; lane final report 2026-10-21)

**Scope and method.** Full clean-room attribution of every blocked row in
`blocked-catalog-rt1.json` (= `blocked-catalog-w4b4.json`, verified
identical per-table, 0 differing tables) over the 151 local-only
reference tables. Method: instrumented `_block` (provides captured
before pop), symbol-chain tracing to terminal state, raw-XML
registration evidence (multi-name `registersymbol(...)`, `label(...)`,
bare labels, Lua `registerSymbol("…")`), per-entry plan-state
cross-reference for the hidden-cascade families, and CE 7.5 source
probes (read-only). Reconciliation: 2,698 = 1,931 REQSYM + 767 direct;
per-table sums over 81 blocked tables plus 1 compile-error table; zero
mismatches. SuperMeatBoy.CT (legacy binary) is excluded from the
2,698 denominator and reported separately at the end.

**Classification legend.** (a) real missing semantics — CE 7.5 handles
the construct, CT2Trainer blocks it. (b) conservative false positive —
CE 7.5 tolerates it, CT2Trainer is stricter. (c) deliberate
duplicate-provider / safety policy — CT2Trainer's own gate, not a
parity gap per se. (d) authoring gap / input-legacy — CE 7.5 also
fails, or the row requires user-side configuration, or the table
targets a newer CE.

**Per-class root-cause table.** Classes are partitioned by immediate
terminal reason (each row exactly once; counts sum to 2,698).
"Delta" = rows whose immediate block this class removes; upstream
roots of the UNDEFINED family (R3) span packages and are noted, so
deltas across classes are not additive.

#### REQSYM rows (1,931)

| Class | Count | Tables (spread) | Upstream root cause | cls | Testable contract (assertion) | Risk | Delta | RT-4 pkg |
|---|---|---|---|---|---|---|---|---|
| R1 DUPPROV_CASCADE | 624 | HellPie 120, Scorn 120, AtomicHeart v1.2 120, Oregon 120, Callisto v1.2 120, qt-ds-1 9, qt-ds-2 6, Cyberpunk 6, ForgottonAnne 2, SHProto 1 | The symbol's provider entry is itself blocked as a duplicate provider (keep-first), so the symbol loses its provider and every dependent record cascades. character_pointer 600 (five UE5 "Esau" template tables sharing the `aobscanmodule(Entity_Player, isaac-ng.exe)` template script; kept production script lacks the full symbol list), inject 16, weaponptr 6, originalcode11 2 | c | A second entry registering an already-registered symbol is not blocked wholesale; its non-duplicate registrations still take effect; first registration wins (CE `registeredsymbols.Duplicates := dupIgnore`) | low-med | 624 (+ ~48 dup-rooted rows inside R3) | RT-4.1 |
| R2 WILDCARD_CASCADE | 3 | Octopath2 ×3 | Provider entry blocked: "Program cannot combine wildcard cleanup with externally owned symbol mem0x04" | c | A wildcard-cleanup program stays supported alongside externally owned symbols; the wildcard is scoped to program-owned symbols at runtime | low | 3 | RT-4.1 |
| R3 UNDEF_AA_HIDDEN | 963 | DSDC 121+120, re2_testicles 114, DS2 110, Witcher3 89+87, Horizon 63+63, Subnautica_e67616 32, LikeADragonGaiden 26, ctts 25, SandFall×5 34, Kena 12, AtomicHeart v1.2 21, re2 7, SOTTR 7, recolored 6, Octopath1 6, ForgottonAnne 5, Cyberpunk 4, APlagueTaleRequiem 3, Cronos 3, SonicFrontiers 2, RiftApart 2, Fallout4 1 | Symbol is statically registered in the table XML, but its provider entry is blocked before symbol extraction. Verified per-family roots (entry-level cross-reference): DSDC 241 — digit-leading label `0CurrentWeight:` inside the big provider script (b); re2_testicles 114 — cleanup-ownership chain pAttackInfo→damageHandle1AOB→pPlayer→entry 12997 (c) plus dCusWetAmount dup-label (b); DS2 110 — cleanup-ownership (c) + group-heading activation not executed, entry 87578 "Navigation heading; CE group activation is not executed" (c) + quoted `"ds.exe"+offset` defines (a) + Trampolines/g_Instance Lua-registered (a); Horizon 126 — Trampolines + component symbols Lua-registered (a); Witcher3 176 — dup `return` inside one `label()` list (b, 148) + x87 `st(0)` FPU operand misparsed as symbol `st` (b, 26) + GetAsyncKeyState (a, 2); Subnautica_e67616 32 — `aobscanregion` + Type:Member bounds (a); LikeADragonGaiden 26 — dup provider (c); ctts 25 — cleanup-ownership (c); SandFall 34 — indirect data dialect (a); Kena/Cronos/re2/DS2 parts — cleanup-ownership (c); AtomicHeart v1.2 21 — dup provider (c); SOTTR 7 — API + dup + dqword (a/c/d); recolored 6 — dotted symbols (b); Octopath1 6 — digit-leading labels (b); ForgottonAnne 5 — usemono (d) + API (a); Cyberpunk 4 — quoted-atom rule (a); APlagueTaleRequiem 3 — FindWindowA (a); SonicFrontiers 2 — unterminated comment (d); Fallout4 1 — dqword (d) | mixed a/b/c/d | Every corpus symbol has a supported provider entry in the plan or is runtime-resolvable (Lua); provider entries blocked only by fixed roots still contribute their symbols | med | 963 (roots span RT-4.1/3/5/6) | RT-4.2 |
| R4 UNDEF_LUA_RUNTIME | 110 | DS2 30, Horizon 39+39, RiftApart 2 | Symbols registered only at attach time via table Lua `registerSymbol("…")` (verified in source): Trampolines, g_GameModule, g_DSPlayerSystem, g_GameState, g_DebugSettings, g_DifficultyManager, g_Viewport, g_AIManagerGame, g_WorldTimer, g_MenuModule, g_PlayerProfile, g_TrophySystem, Player__GetLastActivatedCamera, CharacterProgressionComponent_AddXpBool, CombatRewardsComponent_GetLevel, HeroHealthVFTable | a | An address expression referencing a Lua-registered symbol compiles staged and resolves after table Lua runs at attach | med | 110 | RT-4.2 |
| R5 UNDEF_NO_REG | 91 | GoW 32, DS2 28, 小猫咪 14, Horizon 3+3, RiftApart 5, YLILWin64 3, AtomicHeart v1.2 2, AtomicHeart 1 | No registration anywhere in the table source (not even quoted). In CE these resolve only via user-side symbols, cross-table loading, or undiscoverable dynamic Lua (GoW: Lua AOB-loop registration, traced) | d | A referenced-but-unregistered symbol surfaces as an actionable "undefined provider" with source location; optional user-symbol import covers user-defined cases | low | 91 (partially via user-symbol import) | RT-4.6 |
| R6 UNDEF_LEGACY | 128 | BaseAddress 80 (5 UE5 tables ×16), Inf 5, LikeaDragonIshin 15 (module name without .exe), Fallout4 stats 9, SOTTR 3, trine1 2, Witcher3 2 (st — FPU misparse), BioShock 2, Horizon 2, Kena/ctts/RAGE2/TheSinkingCity/RadiantSilvergun/LustForDarkness/Yakuza/HellPie 9 | User-expected / legacy symbols; no built-in CE 7.5 handling (BaseAddress probed: no Delphi handling — user/Lua symbol). The two Witcher3 `st` rows are actually the x87 `st(0)` FPU-operand misparse (b) | d | Legacy symbols produce an actionable per-symbol "no provider; expected from user config" report; `st(0)` FPU operand tokenizes as a register, not a symbol | low | 128 (2 via the FPU fix) | RT-4.6 |
| R7 UNDEF_API_EXPORT | 12 | GetAsyncKeyState 10 (BatmanAK, DS2, ForgottonAnne 2, SOTTR 2, trine2 2, Witcher3 2), FindWindowA 2 (APlagueTaleRequiem, Resonance) | Windows API exports are not resolvable in the static expression parser; CE resolves them via module export/symbol lists | a | `GetAsyncKeyState` / `FindWindowA` as address expressions resolve to the export address from the target export table; fail closed with an actionable message when absent | low | 12 (+ ~10 API-rooted rows inside R3) | RT-4.2 |

#### Direct (non-REQSYM) rows (767)

| Class | Count | Tables (spread) | Upstream root cause | cls | Testable contract (assertion) | Risk | Delta | RT-4 pkg |
|---|---|---|---|---|---|---|---|---|
| O1 RELADDR_SKIP | 331 | Octopath2 327, AtomicHeart v1.2 1, DS2 1, Horizon 2 | WP-50 relative-address adoption cannot skip an addressless script/value ancestor between the record and the address-bearing ancestor (written by a supported script at runtime) | a | A relative-address record with one or more addressless ancestors under an address-bearing ancestor is staged with runtime-relative resolution | med | 331 | RT-4.3 |
| O2 DUPPROV_DIRECT | 186 | SOTTR 38, Borderlands3-V10 14, ForgottonAnne 11, qt-ds-1 9, qt-ds-2 9, APlagueTaleInnocence 7, +32 tables | Keep-first duplicate-provider policy (WP-37); CE `dupIgnore` keeps first registration and lets the rest of the later script run | c | Same as R1 | low-med | 186 | RT-4.1 |
| O3 PTR_OFFSET_HEX | 53 | Cyberpunk 30, Callisto V1.1 9, working.ct 9, SOTTR 3, Horizon 2 | Pointer-offset slots holding symbol expressions (e.g. `itemQuantityOffset`, UE property paths); CE evaluates offsets as runtime expressions | a | A pointer offset that is a valid address expression resolves at runtime against the symbol table; hex literals keep working | med | 53 | RT-4.3 |
| O4 TRAILING_TOKENS | 43 | DS2 10, GingaForce 8, Subnautica.CT 6, YLILWin64 3+3, Borderlands3-V10 4 (Lua/C primary), DSDC 2, Pennys 3, REZ 3, qt-ds 2+2, rayman 1 | Atoms the expression parser cannot tokenize: quoted-module+offset defines (`define(address,"ds.exe"+26D0389)`) 25; IL2CPP Type:Member defines (`TechData:get_craftAmount`, `PaywallUnlockHelper:get_PaywallUnlockCost`) 12; digit-leading label `0CurrentWeight:` 2; qt-ds/rayman 5 (root unverified, caveat) | a/d | `define(address, "module.exe"+0x123)` resolves via the module base; colon-symbol defines resolve when a symbol of that name is registered | med | 43 | RT-4.3 |
| O5 CLEANUP_OWNED | 31 | DS2 13, re2_testicles 3, ctts 2, Starfield 2, trine2 2, Cronos/Fallout4/Horizon/Kena/re2 8 | Program cleanup section references symbols/allocs not owned by the program; CT2Trainer policy forbids cross-program cleanup; CE permits it unconditionally | c | Cleanup touching only owned symbols passes; foreign references are reported with the owning program (policy kept; diagnostics actionable) | high if relaxed; low for diagnostics only | 31 (+ ~216 cascade rows inside R3) | RT-4.5 |
| O6 DROPDOWN_WIDTH | 30 | P3R 9, P3R-v4 9, P3R-v5 9, P3Reload 3 | Choice literal ('314'/'300') exceeds the Byte value-type width; CE `SetValue` truncates (see CE conclusions) | b | A dropdown choice parsing as an integer is accepted on a Byte record and written as value mod 2^8 | low | 30 | RT-4.4 |
| O7 STRING_SHOWASHEX | 15 | DS2 9, Horizon 3+3 | String value record with ShowAsHex byte view; staged runtime requires literal-text display | a | A string record with ShowAsHex stages a byte-array value; writes accept hex byte sequences | low | 15 | RT-4.4 |
| O8 DROPDOWN_EXPR | 13 | Borderlands3-V10 12, P4G 1 | Dropdown choice values are expressions, not literals; CE `SetValue` evaluates math/Lua expressions in values | a | An expression dropdown choice evaluates at write time against the runtime symbol table | med | 13 | RT-4.4 |
| O9 RELADDR_NO_ANC | 10 | SOTTR 10 | Relative address with no address-bearing ancestor at all in the tree | a | A relative-address record with no static address-bearing ancestor stages as address-required-at-runtime (user- or script-supplied), not blocked | low-med | 10 | RT-4.3 |
| O10 SYM_CHARS | 8 | recolored 5 (dotted symbols `_._`…`_....._`), Octopath1 2 (`8PathBattleResult`, `8PathSteal`), RDR2 1 (nested-comment row) | Identifier strictness: digit-leading names and dots rejected; CE `label()` check `val('$'+name)` rejects only pure-hex names, and symbol names with dots pass. The RDR2 row's root is nested `{}` comments, which CE also fails | b (RDR2: d) | Digit-leading and dotted symbol names are accepted unless the name parses fully as hex (`label()` case, CE `rsIsNotAValidIdentifier`); nested `{}` comments are reported as invalid input, matching CE | low | 8 (+ 253 same-root rows inside R3) | RT-4.3 |
| O11 CUSTOM_TYPE | 6 | re2 3, re2_testicles 3 | RE2_Hrs/RE2_Mins/RE2_Secs custom value types; deliberate AP-08.7 converter/write-gate | c | RE2_* custom types stay staged behind the AP-08.7 gate until a converter/write gate exists | n/a (gated) | 0 until gate | RT-4.4 |
| O12 AOBSCANREGION | 5 | Subnautica_e67616 5 | `aobscanregion` directive (bounds given as Type:Member symbols) unsupported; CE supports the directive | a | `aobscanregion(name, start, end, pattern)` with registered symbol bounds scans the region and registers the symbol | med | 5 (+ 32 rows inside R3) | RT-4.5 |
| O13 INDIRECT_DATA | 5 | SandFall×5, 1 each | Pointer expression `'aobAppendString+7+(DWORD)[aobAppendString+3]'` in the record data dialect; CE symhandler resolves pointer chains in record addresses | a | An indirect data expression in the data dialect resolves at runtime (CE pointer-chain semantics) | med | 5 (+ 34 rows inside R3) | RT-4.3 |
| O14 LUA_C_DIRECTIVE | 4 | Borderlands3-V10 4 | Inline `{$lua}`/`{$c}` (compiler/preprocessor) directives inside AA scripts; CE supports them | a | Inline `{$lua}…{$/lua}` and `{$c}…{$/c}` sections in AA scripts are executed/evaluated (or staged as runtime sections) | med | 4 | RT-4.5 |
| O15 USEMONO | 4 | ForgottonAnne 2, 小猫咪 2 | `usemono()` directive — zero hits anywhere in the CE 7.5 tree (newer-CE directive) | d | `usemono` is reported as targeting a CE newer than 7.5, out of parity scope (stays blocked with a clear message) | n/a | 0 (out of scope) | RT-4.5 |
| O16 DUP_LABEL | 4 | Witcher3 ×2 (dup `return` inside one `label()` list), re2 1, re2_testicles 1 (`dCusWetAmount`) | CT2Trainer per-program duplicate-label guard rejects a repeated name inside one `label()` declaration; CE re-verifies each listed name harmlessly (only multiple `name:` definitions raise) | b | `label(a b a)` with exactly one `a:` definition in the code is accepted; multiple `name:` definitions still rejected (CE rsLabelIsBeingDefinedMoreThanOnce); a name with no definition still rejected (rsLabelIsNotDefinedInTheScript) | low | 4 (+ 148+3 same-root rows inside R3) | RT-4.1 |
| O17 WILDCARD_DIRECT | 3 | Octopath2 3 | Direct wildcard-cleanup conflict rows (see R2) | c | Same as R2 | low | 3 | RT-4.1 |
| O18 ALLOC_MISC | 3 | AtomicHeart 1 (unbalanced directive arguments), P3R-v4 1 (reassemble invalid argument count), Shinkansen Sunless Sea V1005 1 (Type:Member atom `:get_Level`) | Sub-errors inside alloc/reassemble directive handling | a | alloc/reassemble argument validation matches CE grammar; Type:Member atoms per the O4 rule | low-med | 3 | RT-4.5 |
| O19 GLOBAL_INIT | 2 | Resonance 1, TheSinkingCity 1 | Global initialization requires one direct ENABLE cursor; the tables' shape is outside that profile | a | Global-initializer profile accepts the tables' cursor shape (one direct cursor to a supported target) | med | 2 | RT-4.5 |
| O20 NO_EXEC_PATCH | 2 | SOTTR 2 | Enable section contains only `luaCall(lua_aobscan(...))` — Lua-driven symbol registration, no byte patch; CE executes such scripts fine (symbols registered at runtime) | b | An enable section whose content produces symbols via luaCall/registration counts as executable content and is staged | low | 2 | RT-4.5 |
| O21 GLOBAL_INIT_LABEL | 2 | TheSinkingCity 2 | Labels inside a global initializer are outside the direct-literal profile | a | Labels inside global initializers resolve per the profile | med | 2 | RT-4.5 |
| O22 CREATETHREAD | 2 | Witcher3 ×2 | `createThread()`/`threadWait()` gated: no thread backend in the native staged runtime (deliberate capability gate) | c | `createThread`/`threadWait` remain gated with the explicit reason until a thread backend ships | n/a (gated) | 0 until backend | RT-4.5 |
| O23 QUOTED_ATOM | 1 | Cyberpunk 1 | Quoted-atom rule on a script carrying a `$proces` typo (module symbol misspelled) | a/d | Quoted atoms must be resolvable module basenames; otherwise rejected naming the offending token | low | 1 | RT-4.3 |
| O24 ASSERT_ARGS | 1 | Cyberpunk 1 | Assert argument-count check in a hybrid `{$lua}` entry (partially verified, see caveats) | a | Assert argument validation matches CE `assert()` semantics | low | 1 | RT-4.5 |
| O25 BLOCK_COMMENT | 1 | SonicFrontiers 1 | Unterminated source block comment; CE's single-pass comment stripping also fails on it | d | Unterminated `{` comments are reported as invalid input, matching CE | low | 1 | RT-4.5 |
| O26 DROPDOWN_EMPTY | 1 | 小猫咪 1 | Read-only dropdown with no concrete literal choices (description-only) | a | Description-only/read-only dropdowns stage as read-only views without literal choices | low | 1 | RT-4.4 |
| O27 OTHER | 1 | Sunless Skies 1 | `Invalid address expression near ':set_EffectiveLevelM'` — IL2CPP Type:Member atom in an address expression | a/d | Type:Member atoms resolve only when a symbol of that exact colon-name is registered; otherwise actionable error | low | 1 | RT-4.3 |

**Totals.** REQSYM: 624+3+963+110+91+128+12 = 1,931. Direct:
331+186+53+43+31+30+15+13+10+8+6+5+5+4+4+4+3+3+2+2+2+2+1+1+1+1+1 = 767.
Grand total = 2,698.

### RT-4 package split (sums to 2,698)

| Package | Scope | Classes (rows) | Total |
|---|---|---|---|
| RT-4.1 Symbol provider fidelity | CE `dupIgnore` semantics (keep-first without blocking the duplicate provider), repeated names inside one `label()` list, wildcard-cleanup scoping | R1 (624), R2 (3), O2 (186), O16 (4), O17 (3) | 820 |
| RT-4.2 Runtime provider model | Runtime symbol resolution: Lua-registered symbols, hidden provider entries unblocked by their roots, API-export resolution | R3 (963), R4 (110), R7 (12) | 1,085 |
| RT-4.3 Address expression & identifier dialect | Relative-address skip/adoption, expression pointer offsets, trailing-token atoms (quoted module+offset, Type:Member), indirect data dialect, identifier strictness, quoted atoms | O1 (331), O3 (53), O4 (43), O9 (10), O10 (8), O13 (5), O23 (1), O27 (1) | 452 |
| RT-4.4 Value semantics | Dropdown width truncation (CE parity), expression dropdowns, description-only dropdowns, ShowAsHex strings, custom-type gate | O6 (30), O8 (13), O7 (15), O11 (6), O26 (1) | 65 |
| RT-4.5 AA directive & script coverage | Cleanup-ownership diagnostics, aobscanregion, `{$lua}`/`{$c}` directives, usemono newer-CE reporting, alloc sub-errors, global-init profiles, createthread gate, assert args, comment handling, no-executable-patch acceptance | O5 (31), O12 (5), O14 (4), O15 (4), O18 (3), O19 (2), O20 (2), O21 (2), O22 (2), O24 (1), O25 (1) | 57 |
| RT-4.6 Input legacy & authoring gaps | No-provider symbols (user config / cross-table / dynamic Lua), legacy symbols (BaseAddress, stat names, register-like tokens, module names without .exe) | R5 (91), R6 (128) | 219 |
| **Total** | | | **2,698** ✓ |

Package status (2026-10-23): **RT-4.4 done** — catalog remeasure
`blocked-catalog-rt44`: **1,807 blocked** of 117,634 (net -51 over the
RT-3 baseline of 1,858: 51 unblocked, 0 newly blocked, 8 rows
reason-changed onto their pre-existing symbol-provider block; detail in
the RT-4.4 update in the investigation queue above). History: RT-3
(2026-10-23) cleared the one legacy-binary load error (151/151 load,
1,858 blocked of 117,634); RT-4.1 (2026-10-22, remeasure
`blocked-catalog-rt41`) 2,698 -> 1,858 of 117,624 (net -840: 842
unblocked, 2 explained Cyberpunk shared-global regressions). Next
packages by suggested order: RT-4.3 address expression & identifier
dialect (452), RT-4.5 AA directive & script coverage (57), RT-4.6 input
legacy & authoring gaps (219), RT-4.2 runtime provider model (1,085,
last).

Suggested execution order: RT-4.1 (820, lowest risk and the largest
guaranteed delta) first, then RT-4.3 (452), RT-4.4 (65), RT-4.5 (57),
RT-4.6 (219), and RT-4.2 (1,085) last — its AA_HIDDEN portion clears
progressively as the root packages land, and the residual is runtime
provider work. Remeasure the catalog after each package (roadmap rule).

### CE 7.5 behavioral conclusions (read-only reference, probes closed 2026-10-21)

1. **Dropdown value overflow: truncation, not refusal.**
   `TMemoryRecord.SetValue(v, isFreezer)` (MemoryRecordUnit.pas:3200–3574):
   for integer types (`vtByte..vtDouble`, `vtCustom`) the value string is
   parsed with `StrToQWordEx(currentValue)` and stored through the typed
   pointer (`pb^ := v64` for Byte) — CE **truncates** an out-of-range
   choice to the record's byte width and never refuses it (choice '314'
   on a Byte writes low byte 0x3A = 58); only unparseable strings raise.
   Conclusion: the DROPDOWN_WIDTH refusals (O6, 30 rows, P3R '314' /
   P3Reload '300' over Byte) are conservative false positives → (b);
   contract = accept the literal, write value mod 2^bits. The same
   SetValue path evaluates `[...]` Lua/math expressions in values, which
   independently grounds O8's (a) classification (expression dropdowns
   are a real CE capability CT2Trainer lacks).
2. **Module reference without .exe.** `TSymhandler.getAddressFromName`
   (symbolhandler.pas:4985–5103): each token is tried as hex, then
   `getmodulebyname(token)` — an **exact** match against module names
   stored via `extractfilename` (extension kept, uppercased) — then Lua
   symbol callbacks, registers, the symbol list. A bare module name
   without `.exe` (LikeaDragonIshin, 15 rows across the two table
   versions) matches no module → **fails in CE 7.5 too**, unless the
   user configured a common-module-list alias or a same-named symbol
   exists. Conclusion: (d) input-legacy / user-config-dependent;
   extension-tolerant module matching could be added as a convenience
   but is not required for 7.5 parity.
3. **IL2CPP Type:Member resolution.** Zero IL2CPP references in any CE
   7.5 Delphi (.pas) or Lua source; IL2CPP code exists only in the
   standalone pipe-server C (PipeServer.cpp/h, ~161 hits — an
   external-process feature with no table-facing expression resolution
   in 7.5). `Type:Member` atoms in address expressions resolve **only
   if a symbol of that exact colon-name is registered** (user symbol
   configuration or table Lua). Conclusion: the ~19 Type:Member rows
   (Subnautica.CT 6, YLILWin64 ×2 ×3, Shinkansen Sunless Sea 1, Sunless
   Skies 1) are not static-semantic gaps against 7.5 → (d) tables
   targeting newer-CE or user-configured symbol resolution; the
   `aobscanregion` directive itself (O12, 5 rows) is a real 7.5 feature
   → (a).

**Supporting CE 7.5 findings used above:**

- `registeredsymbols.Duplicates := dupIgnore` (autoassembler.pas:338/345)
  — duplicate registrations keep the first silently.
- `label()` identifier check `val('$'+name)` rejects only names that
  parse fully as hex (autoassembler.pas:2577–2578); the
  duplicate-declaration check is commented out (2585–2586); multiple
  `name:` definitions in the code raise rsLabelIsBeingDefinedMoreThanOnce
  (2599); a never-defined name raises rsLabelIsNotDefinedInTheScript
  (2603).
- `removecomments` (autoassembler.pas:732–798) is a single-pass state
  machine without nesting support → nested `{}` comments break in CE as
  well.
- `usemono`: 0 hits anywhere in the 7.5 tree → newer-CE directive.
- `BaseAddress`: no built-in handling in the Delphi sources →
  user/Lua-defined symbol.

### Caveats

1. Five trailing-token rows (qt-ds-1/qt-ds-2 ×2 each,
   raymanlegends_dvt 1) could not be inspected entry-wise (scripts not
   retrievable by plan entry ID) → root unverified; counted under O4.
2. Cyberpunk O24 (assert argument count, entry 159): the assert lives in
   a hybrid `{$lua}` section whose body was not fully dumped → (a)
   classification is from the reason shape; details unverified.
3. Borderlands3-V10 O8 rows (12): the dropdown choice values were not
   extracted from the XML (different DropDown markup) → classified by
   reason text; the CE SetValue expression-evaluation evidence is solid
   regardless.
4. The DS2 myPtr family (44 rows) has multiple provider entries blocked
   for different reasons (cleanup-ownership, trailing tokens,
   group-heading activation, REQSYM) — any single root fix resolves
   those rows; per-class deltas are therefore not additive.
5. The two Witcher3 `st` rows sit in R6 (legacy) for strict partitioning,
   but their true root is the FPU `st(0)` operand misparse (b) — the
   tokenizer fix resolves them together with the 26-row player_ptr chain
   (R3).
6. All counts are over run `w4b4-case30-20261020081722Z` / the RT-1
   rebaseline (identical per-table catalog); the 42/42 synthetic feature
   matrix is unaffected.
7. **SuperMeatBoy.CT (excluded):** legacy-binary table with 1 compile
   error (`compile_error_count=1` in both catalogs); its rows are not
   catalogable in the reference format and must be handled via the
   legacy-binary path, not an RT-4 package. Excluded from the 2,698
   denominator by definition.


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
