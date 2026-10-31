# Reference-table 100% roadmap

Status: 2026-10-24. Active plan after the 0.16 Wave 4 release; RT-3
(legacy-binary CT loading) and RT-4.4 (value semantics) landed 2026-10-23,
RT-4.1 (symbol provider fidelity) landed 2026-10-22, and RT-4.6 (input
legacy & authoring gaps) and RT-4.5 (AA directive & script coverage)
landed 2026-10-24. Catalog remeasure `blocked-catalog-rt45main`:
1,743 blocked of 117,634 plan entries, 151/151 tables load. The older AP/WP plans record completed implementation
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
| RT-4 | Close high-volume plan gaps | Execute the RT-2 root-cause-map packages in suggested order by expected delta over risk: RT-4.1 symbol provider fidelity (dupIgnore policy, dup labels, wildcard-cleanup scoping) 820 — done 2026-10-22 (remeasured 2,698 -> 1,858 blocked), RT-4.3 address expression & identifier dialect 452 — done 2026-10-26 (remeasured 1,743 -> 1,351 blocked), RT-4.4 value semantics 65, RT-4.5 AA directive & script coverage 57, RT-4.6 input legacy & authoring gaps 219, RT-4.2 runtime provider model 1,085 (last: its AA_HIDDEN portion clears progressively as root packages land) - done 2026-10-27 (remeasured 1,351 -> 1,053 blocked). The split sums to 2,698. Each package: leading-table inspection, an independently authored synthetic case, the class contract as a testable assertion, owned-target runtime tests where effects matter, full suite, catalog delta with zero unexplained supported regressions, and a remeasure. A reason count is not an independent feature count; remeasure after each fix. |
| RT-5 | Runtime trainer parity | Inventory every used CE Lua/AA API and game-facing table-level construct, including dynamic records, callbacks, target threads, managed resolution, string hex view, and byte-width dropdown semantics. Implement each needed behavior with bounded contracts, teardown rules, and owned-target tests; classify purely visual UI as outside scope. — done 2026-10-31 (all inventory items A, B, C, C2, D, E, F, G landed: F+G 2026-10-26, A+C 2026-10-28, C2+D 2026-10-29, B+E 2026-10-31; final catalog `blocked-catalog-020-rt5-be`: 1,053 blocked of 117,809 plan entries, 116,756 supported including the 175 code-patch entries, zero newly blocked at every step). |
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

Update (2026-10-24, RT-4.6): the input-legacy & authoring-gaps package
landed (branch `native-rt4-6`, merged to `main` the same day; clean
three-way merge over the RT-4.4 + 0.16.4 state, no conflict resolution).
Three clean-room changes: (a) R5/R6 UNDEF_NO_REG / UNDEF_LEGACY closure —
in `_dependencies`' zero-candidate branch, a required symbol with no
supported record provider and no UDS/table-Lua/user-symbol fallback now
receives the actionable per-symbol report `Required symbol '<S>' is not
registered anywhere in this table (referenced by '<record path>'): no
record defines it and it is not a user-defined symbol. Import it as a
user symbol with its target address, or add a record that registers it
(registersymbol/registerSymbol/label/aobscan).` when the raw-source
registration survey (`_symbol_source_survey`: registersymbol /
registerlabel / registerSymbol call forms including quoted names,
line-anchored `label(...)`, `define(...)` + `{$define ...}`, positional
`name:` labels, `aobscan*(...)` first argument — pure text, fail-safe
direction: malformed syntax can only add registration evidence, never
remove it) finds no registration anywhere; the generic `Required symbol
has no unique supported provider: S.` stays byte-identical when a
registration exists or several providers compete (the plan cannot make
this distinction itself because `_block()` clears `provides`). (b) R6
legacy-tokenizer fix — the x87 FPU operand `st`/`st(N)` (CE
Assemblerunit.pas:3283-3291 parity) now folds to register tokens
st0-st7 in the AA tokenizer (bare `st` -> st0; exactly one digit
`st(N)` -> stN); `st(8)`+ keeps the bare token so the symbol machinery
blocks fail-closed. (c) user-symbol import — `compile_table(
user_symbols=...)`, `load_user_symbols(path)` (JSON name -> 64-bit
unsigned address; bounded, named, fail-closed refusals) and CLI
`--user-symbols FILE` on inspect/prepare/build; plan field
`user_symbols` (residual rule identical to the UDS field: only symbols
no supported record provides, casefolded keys, sorted); the engine seeds
UDS first, then user symbols, on init and every confirmed attach; both
plan validators refuse forged maps (shadowing record-provided symbols,
out-of-range values, duplicates). Tests: 53 new (9 + 12 + 32) in
`tests/test_native_fpu_st_operand.py`,
`tests/test_native_undefined_provider_report.py`,
`tests/test_native_user_symbol_import.py`, plus pin updates in
`test_native_creator_inspection`, `test_native_luacall_symbol_provision`
(x3) and `test_native_placeholder_aob`. Full suite on `main` after the
merge: **3,532 OK / 25 expected skips** (baseline 3,479 + 53; clean
re-run exit 0). Catalog remeasure (local, run `blocked-catalog-rt46`,
frozen manifest and process bindings unchanged): **1,807 -> 1,778
blocked** of 117,634 (net -29; supported 115,827 -> 115,856; staged
59,683 -> 59,709; 151/151 tables load, zero compile errors). Exactly 29
rows unblocked: Lust from Beyond -F id=8 (`st`) and Witcher3 4.02HF1 x14 /
4.03 x14 (per table: `st` 1 at id=10070, plus the cascade behind the
now-supported 'Activate Player Scripts' provider — player_ptr 11,
companion_ptr 1, horse_ptr 1). Zero newly blocked rows. 218 rows change
only their block reason and stay blocked on the same gate: all 218 move
from the generic provider message to the actionable per-symbol report
(the lane's 217 over the RT-3 baseline plus the RT-4.4 reason-changed
小猫咪 id=3 `CatValues` row, which now also qualifies); 0 rows change
back to generic. Lane classification audit over all 1,284 zero-candidate
rows: 1,038 generic / 217 new-style / 0 misclassified. Documented
deviations beyond the R5/R6 split: +2 RiftApart `HeroHealthVFTable` and
+2 Witcher3 `str_base` (legitimately unregistered -> new-style); DS2
`InventoryItemProperties_call_dest` and Horizon Forbidden West `Sleep`
x2 stay generic (bare call targets). Known root-owned defect (out of
lane scope): the pinned NASM 3.02 mis-encodes the FSTP fpureg table
entry (`x86/insns.dat:751` `FSTP fpureg [r: dd d8+r]`, correct is
`df c0+r`) — measured `fstp st0` -> `DD D8` instead of `DF C0`
(`fcomip st0, st1` -> `DF F1` is correct); the two Witcher3 `fstp
st(0)` rows (one per 4.0x table) therefore link but assemble with wrong
bytes until root re-pins or locally patches the NASM dependency
(authorized local-fork path per `AGENTS.md`). Resolution (root audit
2026-10-26, see native-progress "NASM 3.02 FSTP encoding audit"): no
defect in the pinned NASM 3.02 - `DD D8+i` IS the correct encoding of
FSTP ST(i) per the Intel SDM table (verified with the pinned MIT
iced-x86 decoder); the original "expected DF C0" reading was wrong, and
the spurious 0x66/0x67 prefixes in probe output came from test snippets
without an explicit `bits` directive (this build defaults to 16-bit).
Witcher3 `fstp st(0)` rows assemble correctly end-to-end; regression
pins added to `tests/test_native_fpu_st_operand.py`.

Update (2026-10-24, RT-4.5): the AA directive & script-coverage package
landed (branch `native-rt4-5`, merged to `main` the same day after the
RT-4.6 merge; clean three-way merge, no conflict resolution). Changes:
(a) O12 AOBSCANREGION — `aobscanregion(name, start, end, pattern)` with
Type:Member symbol bounds supported; the `dealloc` name-list follows CE
7.5 (comma/whitespace split, silent unknown-name drop, 128-name/128-char
bounds, a wildcard takes no other names, numeric size tail tolerated),
while cross-program cleanup keeps the ownership-gate refusal as a
documented deliberate divergence; (b) O15 USEMONO — both envelope halves
refuse `usemono()` with the named parity-scope message (zero CE 7.5
hits); (c) O18 managed-label regex admits the three-segment
`Namespace.Class:BaseClass:Method` form (`{1,2}` colon tail); two-,
`::` and four-segment forms stay refused; (d) O19 GLOBAL_INIT — global
DISABLE reset regions (no-op reset on an initialized global whose
repeated literal bytes equal the ENABLE initializer; empty regions
accepted; changed bytes refused as changed re-initialization);
(e) O20 NO_EXEC_PATCH — symbol-only static envelopes (DISABLE-only
`unregistersymbol` of the record's own luaCall AOB symbols admitted via
the `symbol_only_disable` marker, two-pass `_release_owned_unregister`,
plan-level one_shot True / record-level False); (f) O21 — label after
consumed literal data closes the global region into the consumer
program, label before data keeps the refusal; (g) O5 diagnostics — named
symbol-handover refusals carry the single owning record id via
`external_owners` at all three re-derivation sites; pure-global records
get the canonical empty consumer program (manager-less pool round trip,
`global_alloc.empty_consumer_program`). Tests: 30 new (17 + 5 + 4) in
`tests/test_native_global_reset.py`,
`tests/test_native_luacall_symbol_only.py`,
`tests/test_native_aa_named_refusals.py`, plus pin updates in
`test_native_assembler`, `test_native_address_tokens`,
`test_native_managed_method`, `test_native_aa_literals` and
`test_native_lua_symbol_handover`. Full suite on `main` after the
merge: **3,562 OK / 25 expected skips** (clean re-run exit 0). Catalog
remeasure (local, run `blocked-catalog-rt45main`, frozen manifest and
process bindings unchanged): **1,778 -> 1,743 blocked** of 117,634
(net -35; supported 115,856 -> 115,891; staged 59,709 -> 59,735;
151/151 tables load, zero compile errors). Exactly 35 rows unblocked:
Subnautica_e67616 x28 (4 `aobscanregion` rows plus 24 cascade rows whose
providers the supported directive now registers), TheSinkingCity x2
(O19 id=14780, O21 id=258093), SOTTR x2 (O20), Resonance x1 (O19),
Shinkansen Sunless Sea V1005 x1 (O18, id=112473) and RDR2 x1
(id=48136). Zero newly blocked rows. Seven rows change only their block
reason and stay blocked: ForgottonAnne id=0/103886 and 小猫咪 id=1/2
onto the named usemono parity-scope refusal; Subnautica_e67616 id=89
onto the ownership gate (deliberate divergence); Sunless Skies id=29
onto the trailing-tokens refusal; TheSinkingCity id=258084 onto the
changed-reinitialization refusal (`bFastTravel`). No supported
regressions.

Update (2026-10-26, RT-4.3): the address-expression & identifier-dialect
package landed (lane `native-rt4-3`, executed by the root integrator
after the lane subagent stalled; rebased onto `main` @ `29adebb`, four
conflicts resolved: main's bounded `{1,2}` managed-label tail from
RT-4.5 (O18) kept, the lane's hyphen-module and digit-leading-symbol
atoms kept, test pins aligned to the merged unregistered-symbol
report). Code: (a) O1 relative-address skip-fold — a relative-address
record under addressless script/value ancestors stages on the nearest
address-bearing ancestor as an expression address (`(1040)+20`,
`address_profile=expression/v1`, no symbol requires); (b) O9
runtime-base markers — group headings carry
`runtime_base_required`/`runtime_base_anchor`/`runtime_base_target`
with a plan-level cross-check that fails closed on forged or dangling
markers, and the engine's `set_dynamic_address(anchor, value,
scope=writer)` is restricted to a supported addressless `kind=script`
writer record; (c) O3 pointer-offset slots accept supported address
expressions (staged verbatim in `pointer_offsets`, resolved against
the live symbol table at activation; hex literals unchanged, malformed
forms keep the expression-aware refusal); (d) O10 identifier dialect —
digit-leading symbol names (`8PathSteal`, `20XX`) and dot-bearing names
are admitted per the CE `label()` contract (`val('$'+name)` stops at
the first non-hex character; fully-hex names stay refused by the
label contract), hyphen module basenames
(`Octopath_Traveler-Win64-Shipping.exe`) tokenize as one atom while
`.exe`/`.dll`-qualified export atoms stay whole (trailing negative
lookahead); (e) O23 quoted atoms must be module basenames and the
refusal now names the offending token (`Quoted atom '$proces' must be
a module basename (.exe/.dll)`); (f) O27/O4 Type:Member managed
labels (`A:B:C`, `Namespace.Class:BaseClass:Method`, tail bounded to
one or two separators per the RT-4.5 O18 form) resolve through the
injected IL2CPP resolver with a per-label named refusal otherwise;
(g) O13 directive-aware string data bytes (`db` one ANSI byte per
char, `dw` UTF-16LE words of any length, `dd`/`dq` ANSI chars packed
little-endian and zero-padded into one unit). Tests: new dedicated
`tests/test_native_address_expression_dialect.py` (20 tests:
export-atom tokenization, identifier/quoted-atom/managed-label
grammar, O3 plan + engine chain with forged-slot fail-closed, O1/O9
staging E2E with forged-marker fail-closed, O27 resolver E2E with
named refusals, O13 byte-exact engine writes over the external-literal
data path) plus 7 pin additions/updates across
`test_native_address_tokens`, `test_native_compiler`,
`test_native_pointer_offset_forms`, `test_native_single_quote_data_literals`,
`test_native_assembler`, `test_native_managed_method`,
`test_native_user_symbol_import`. Full suite on `main` after the
merge: **3,613 OK / 25 expected skips** (clean run exit 0; merge-base
suite 3,590 plus the dedicated dialect file and net lane test
additions). Catalog remeasure (local, run `blocked-catalog-rt43-main`,
frozen manifest `gap_inventory/reference-manifest.json` and process
bindings unchanged): **1,743 -> 1,351 blocked** (net -392; 117,634
total unchanged, supported 115,891 -> 116,283, staged 59,735 ->
59,868, zero load errors). Composition of the 392 unblocked rows by
their old terminal reason: O1 relative-address skip-fold 195, O3
pointer-offset expression slots 51, O4/O27 trailing-token and
Type:Member address-expression atoms 38 (incl. the Sunless Skies O27
row), O10 identifier-dialect direct rows 5 plus 90 dependent rows whose
symbol/provider-lookup terminal reason was cleared by the new grammar,
O9 runtime-base staging 8, O13 indirect data 5. 12 rows
reason-changed while staying blocked (all explained: the token-named
quoted-atom refusal on the Cyberpunk `$proces` row, refined per-symbol
reports, cleanup-ownership report rewording). **Zero newly blocked
rows**, zero supported regressions. The residual O1/O9 rows (136 + 2)
keep their terminal reason: their chain carries no static
address-bearing ancestor — the base is supplied by an addressless
runtime script (RT-4.2 runtime provider model); the O1/O3/O4/O9/O10/O13
grammar roots they carried are fixed.

Update (2026-10-26, RT-5 item G): the `createThread`/`threadWait` backend
decision landed (lane `native-rt5-g`, merged to `main` as `2de9c0e`).
Decision record: option (2) — keep the capability gate, no thread backend
ships this milestone; a bounded owned-thread backend requires a root
design review first (owned-thread lifecycle, debug-event ownership,
join semantics, exact disable teardown, journal receipt — the sketch
lives in the lane report and is input for the next-work roadmap).
Deliverable: `tests/test_native_rt5_thread_gate.py` (17 tests) pinning
the five-stage fail-closed chain byte-stable — tokenizer
(`Unsupported AA directive: createthread.` / `threadwait.`), one-shot
grammar, `prepare_program` staged-runtime gate (`createThread()/
threadWait() are gated in the native staged runtime: no thread backend
is part of the shipped trainer profile.`), the converter composite
reason identical to the launch-base catalog row, preflight/dry-link
injected-backend refusals plus the threadWait-before-createThread
ordering refusal, and the TrainerEngine default-binding
`NativeRuntimeError` with zero allocation/symbol/write side effects;
a positive-control injected-backend roundtrip proves the gate is
exactly the missing binding. Census re-derived (not carried over):
exactly 2 O22 catalog rows at the launch base (Witcher3
4.02HF1_G25v2 + 4.03_G25v2, id 192, "Call Function"); over the
151-path reference corpus, 77 first-word `createThread` usages across
18 tables split into 26 AA directive lines in 8 tables (governed by
the gate) and 51 Lua-context lines in 11 tables (`lua_host`
cooperative workers, a separate family, not O22-gated); zero first-word
`threadWait` lines. Tests only, zero catalog movement (remeasure
`blocked-catalog-rt5g-main` vs `blocked-catalog-rt43tests-main`:
1,351 blocked of 117,634, zero delta). Full suite on `main` after the
merge: **3,648 OK / 25 expected skips**.

Update (2026-10-26, RT-5 item F): the no-effect register ratification
landed (lane `native-rt5-f`, merged to `main` as `966fccd`):
`tests/test_native_rt5_no_effect_register.py` (+22 tests, 12 classes)
turns the RT-5 inventory section-8 no-effect / out-of-scope register
into an enforced, byte-stable contract — the 26 CE UI globals
(inventory section 7.2 minus messageDialog) keep the exact runtime
refusal `Unsupported CE Lua API: <name>` with zero target side effects
(including the uppercase `GetAddressList` vs the hosted lowercase
`getAddressList` contrast, `playSound`, and the legacy timer helpers);
the section-7.3 object-method register is pinned per surface (the WP-56
inert menu/form proxy accepts and discards 14 methods; the addresslist
and memory-scan named refusals; stringlist file access out-of-profile;
structure methods unreachable behind the createStructure refusal); the
table-level Structures, Signature/SignedHash/PublicKey, Forms
(CETrainer/IconList/UDF1) and Files families warn byte-exactly with
sorted `ignored_sections` and are plan-inert (differential plan-state
equality vs a construct-free control); LastState + RealAddress and
Color/Comments/DisassemblerComments are silent; a plain GroupHeader
stays a supported navigation heading; ActivateSound/DeactivateSound
hotkey children are ignored; the usemono() record is blocked with the
exact composite reason. Tests only; zero catalog movement (remeasure
`blocked-catalog-rt5f-main`); full main suite after the merge
**3,670 OK / 25 expected skips**.

Update (2026-10-28, RT-5 item A): the embedded `<Files>` extraction and
Lua-surface package landed (lane `native-rt5-a`, merged to `main` as
`479977c`). New clean-room module `src/ct2trainer/native/embedded_files.py`
implements the CE-7.5 dual-branch codec: an exact `Encoding="Ascii85"`
attribute decodes the CE-alphabet Ascii85 text to a raw-deflate stream
that expands to a 4-byte little-endian size prefix that must equal the
remaining payload; any other or missing `Encoding` value takes CE's hex
branch (hex text -> raw deflate, read until EOF, no size prefix), verified
against `luafile.pas::createFromXML`. Both branches carry named refusals
(empty text, single-character Ascii85 tail, out-of-alphabet / non-hex
character, odd hex count, truncated / invalid deflate, size-prefix
mismatch, content over the 4 MiB per-file bound). The per-file bound is
4 MiB (one `readStringLocal` call must be able to return the whole file,
tracking the per-call transport limit); the per-table total stays at 16 MiB.
`table.py::_parse_embedded_files` decodes every entry fail-closed (a single
undecodable entry aborts the table load with a named `TableError`);
`EmbeddedFile` + `Table.embedded_files` project through `to_dict`.
Duplicate names are tolerated (CE table-load parity); the compiler emits
`embedded_files` casefold-sorted, only when non-empty, and both plan
validators re-derive hash/size from the stored text (schema-1 plans cannot
carry them). The engine seeds `_embedded_files` / `_embedded_by_name` at
init via `setdefault` (case-sensitive exact-name, first-occurrence-wins).
`lua_host` adds the `findTableFile`/`FindTableFile` dispatch (nil when
absent; dual `stream.memory` / `file.Stream` access shapes), `readStringLocal`
(token-based `ct2tf:` / `ct2ss:`, strict UTF-8, wide-string refusal, plus
two documented clean-room deviations — omitted/negative maxsize returns the
full content instead of CE's default 50 bytes, and no NUL truncation because
the content is the asset itself), the `stringstream.*` surface
(create/copyFrom/dataString/size/destroy, per-scope registry bounded at
256 objects / 16 MiB), `tablefile.delete` and `createTableFile` fail-closed
refusals, and the stringlist `Text` getter/setter (CRLF-to-LF, positional
split keeping empty lines, one trailing newline does not add a phantom
item, destroy). A `load`/`loadstring` compat wrapper restricts to string
chunks in text mode (function-chunk and binary-mode refused);
`dofile`/`loadfile`/`coroutine` stay nil. The stringlist `Text` setter had a
`gmatch` bug (no captures returns matched strings, not positions) fixed with
a find-based positional loop. Tests: `tests/test_native_rt5_embedded_files.py`
+53 (codec roundtrip over all tail lengths + hex-branch roundtrip + the exact
named decode refusals; `validate_embedded_files` forgery matrix + hex
acceptance + duplicate tolerance + 64-file / 16 MiB bounds; table-load
contract with hex-branch positive + invalid-hex named refusals + duplicate
tolerance + per-file and total bounds; plan projection casefold-sorted +
both validators' forged-hash/size/schema-1/hex-entry; end-to-end P5
table-Lua shape with a byte-exact 4641 write and disable restore plus the
engine registry seed; the RiftApart record shape
tFileList -> createStringStream -> copyFrom -> stringlist.Text -> loadstring;
readStringLocal maxsize and NUL semantics; invalid-UTF-8 named refusal;
casefold-duplicate case-sensitive resolution; exact-duplicate
first-occurrence-wins; string-stream-token readStringLocal; 12-case refusal
matrix with zero memory writes) plus pin updates in `test_native_lua`
(sandbox `load`/`loadstring` wrapper), `test_native_rt5_no_effect_register`
(`<Files>` no longer in the omitted warnings, exact `embedded_files`
projection) and `test_native_table_completeness` /
`test_native_user_defined_symbols` (`embedded_files` in the completeness
contract). Focused 221 tests across 5 files OK; full suite on `main` after
the merge **3,745 OK / 25 expected skips** (baseline 3,692). Catalog
remeasure (local, run `blocked-catalog-rt5a-main`, frozen manifest and
process bindings unchanged): **zero delta** — 151/151 load, 117,634 total,
116,581 supported (60,161 staged), 1,053 blocked, 0 compile errors, 0 newly
blocked, 0 reason-changed. The reference tables carrying a non-empty
`<Files>` section (9 files / 7 distinct games: P5Strikers + copy, RiftApart,
Octopath2, DeathStrandingDC + compatibility, Cronos, Resonance,
SinkingCity) now gain `embedded_files` in their plans; no record blocking
status moves. `runtime_unverified` remains: the embedded-file record effects
are untested on a live target.

Update (2026-10-28, RT-5 item C): the bounded process-info Lua API family
landed (lane `native-rt5-c`, commit `0167825`, merged to `main` the same
day). Eleven APIs implement the CE 7.5 process-info surface under the
clean-room single-target model — every API answers only from the attached
target (plan process binding, attached pointer width, target module
table, bounded memory disassembly); no OS process or module enumeration
beyond the target. `getProcessIDFromProcessName` (exact/casefold match
against the plan process binding returns the attached pid, anything else
0 — documented deviation from CE's nil; the corpus tolerates both
shapes), `getProcessList` (single-entry pid->name map resolving the
`pl[pid]` and `pairs()` corpus shapes; documented single-target bound),
`getAutoAttachList` (inert per-scope singleton stringlist, fresh per host
run, reset in `cancel_resources`), `getOpenedProcessID` (one-line
passthrough alias of `getOpenProcessID`), `getSettings` (inert settings
object; `Value` answers '' for any missing key — CE parity for a missing
registry value; writes stored on the object and discarded; non-string
section is a named refusal), `integerToUserData` (identity — addresses
are plain integers in the host value model), `targetIs64Bit` (pointer
width 8 -> true, 4 -> false; no arguments), `enumModules` (single-module
answer with Name/Address/Size/Is64Bit/PathToFile; PathToFile falls back
to the EXE name when the backend reports no image path — documented
deviation; covers the GoW `for i=1,#modList` shape), `disassemble`
(bounded iced-x86 exposure over target memory: the CE line shape
`<8-digit hex address> - <hex bytes> - <opcode operands>` in the pinned
iced Intel syntax — documented deviation from CE's uppercase style;
optional second argument count 1..4096 returns the per-instruction line
list — documented clean-room extension with no corpus usage; named
refusals for argument count, count bound, invalid instruction and bounded
read ending first), `stringlist_add` (the CE `strings_add` startup-global
alias, list-first argument order, driving the owned dot-call `.add`
contract, returning the new 0-based ordinal; named refusal for
non-string-list and destroyed list) and `getCEVersion` (ROOT DECISION:
pinned constant string '7.5' — documented deviation from CE's number
answer; tables use it as a CE-version gate and the product implements
the CE 7.5 surface). Wiring exactly like item A: table-scope
`TABLE_LUA_READ_ONLY_NAMES` += the five dispatch names, record-scope
function list += five, `_ReadOnlyBroker._READS` += five so every pure
query is admitted under syntax checking; no plan fields, no engine path
changes. Every out-of-profile call is a named refusal with zero memory
writes and no applied record. Tests: `tests/test_native_rt5_process_info.py`
+23 (byte-exact pid/count/shape markers via writeInteger read-back, x86
plan plus pointer_size=4 memory for the 32-bit targetIs64Bit/enumModules/
disassemble behavior, byte-exact disassemble lines incl. the 5-byte mov
and the 2-line count form, 14-case refusal matrix plus 3 standalone
disassemble refusals with zero memory writes and no applied record,
out-of-scope names still refused, table-scope allowlist admits all five
dispatch reads with a clean bootstrap); focused 23 OK. Full suite on
`main` after the merge **3,790 OK / 25 expected skips** (baseline 3,767).
Catalog remeasure (local, run `blocked-catalog-rt5c-main`, frozen manifest
and process bindings unchanged): **zero delta** vs
`blocked-catalog-rt5a-main` — 151/151 load, 117,634 total, 116,581
supported (60,161 staged), 1,053 blocked, 0 compile errors, 0 newly
blocked, 0 reason-changed. 44 of the 151 reference tables reference at
least one item-C API (getCEVersion 27 tables / 36 calls,
getProcessIDFromProcessName 19 / 35, getProcessList 7 / 14,
getOpenedProcessID 6 / 8, getAutoAttachList 5 / 5, targetIs64Bit 5 / 32,
enumModules 5 / 6, disassemble 3 / 11, stringlist_add 3 / 3, getSettings
2 / 4, integerToUserData 2 / 4); the catalog is unaffected because it is
static plan-level and the APIs are pure runtime host reads.
`runtime_unverified` remains: the API answers are untested on a live
target.

Update (2026-10-29, RT-5 item C2): dynamic addresslist records + custom
AA directives landed (lane `native-rt5-c2`, commit `dbfdcc2`, merged to
`main` as `dde9f04`): `createMemoryRecord` (AddressList /
`getAddressList()` / the built-in AddressList index) creates engine-owned
session journal entries with synthetic IDs >= 2**31 — never persisted
(the state store refuses them), cleared on target exit and close,
bounded at 4096; the record surface implements the CE MemoryRecord
runtime contract the corpus uses (Description/Type/Address incl.
verbatim expression text re-resolved at read/write, Script, Parent with
self-parent/cycle refusal and grandchild promotion on delete, Child[i]
0-based with out-of-range nil, Offset[i]/OffsetText[i] bounded writes,
Count/Index/OffsetCount/isDynamic, Value read/write vtByte..vtDouble,
inert display keys); journal OnActivate/OnDeactivate are 'ct2fn:<n>'
function tokens fired on the real Active transition from the owning
host (stale-scope and callback-failure containment); plan records gain
session-stored OnActivate/OnDeactivate (fired from the shared
enable/disable dispatch) and session-stored display mutations (plan
untouched); getCEVersion now answers the number 7.5 (CE 7.5 LuaHandler
pushnumber parity — supersedes the item-C string pin; the corpus gates
numerically and the string usages coerce through Lua); addresslist
lookups gain getMemoryRecord (integer = flat 0-based position, string =
casefolded description per CE getRecordWithDescription semantics, absent
answers nil), getMemoryRecordByID numeric-string coercion, casefolded
getMemoryRecordByDescription, Count/MemoryRecord[i] out-of-bounds nil,
inert selection no-ops; registerAutoAssemblerCommand/
unregisterAutoAssemblerCommand register table-scope custom AA directives
(built-in names refused, re-registration replaces, registry dies with
the table scope, record-scope registration refused named, expansion in
prepare_program after nested-assembly inlining with {$define}
substitution, bounded results 1 MiB / 4096 lines, nested reprocessing,
strict no-op without a registry, validate/preflight/dry_link/link
revalidated against the same registry, syntaxcheck pass honors the
corpus 'if syntaxcheck then return end' guard idiom). Tests: new
`tests/test_native_rt5_dynamic_records.py` +27 (journal happy path +
plan byte-identity, AddressList/getAddressList forms, Child/Offset
0-based + Delete/destroy/removeFromParent, value read/write, refusal
matrices, GoW OnActivate/OnDeactivate shapes + failure containment,
vtAutoAssembler enable/disable + bad-script refusal, custom directive
end-to-end + replace/unregister + reserved names + invalid args +
registry dies with scope, syntaxcheck refusals, _expand_custom_commands
unit + prepare_program revalidation, journal lifecycle) plus pin updates
in `test_native_rt5_process_info.py` (getCEVersion number, out-of-scope
list moved to C2), `test_native_lua.py` (record.set helper-install
no-op), `test_native_rt5_no_effect_register.py` (getMemoryRecord now
supported, refusal pin superseded), `test_native_table_lua_bootstrap.py`
(record.set records the engine named refusal), `test_native_aa_literals.py`
(prepare_program signature). Full main suite after the merge
**3,817 OK / 25 expected skips** (baseline 3,790). Catalog remeasure
(run `blocked-catalog-rt5c2-main`): **zero delta** vs
`blocked-catalog-rt5c-main` (151/151 load, 117,634 total, 116,581
supported (60,161 staged), 1,053 blocked, 0 compile errors, 0 newly
blocked, 0 reason-changed). `runtime_unverified` remains: journal record
effects and custom-directive expansion are untested on a live target.

Update (2026-10-29, RT-5 item D): the table's onOpenProcess/onTableLoad callback dispatch landed (lane `native-rt5-d`, commit
`fb1253b`, merged to `main` as `9294bb8`): after a clean
table-Lua bootstrap (the `meta['executed']` branch of
`_run_table_lua_bootstrap`, after the `table-lua-executed` event)
the trainer fires the table's CE callbacks on the table-scope host
in the CE sequence — `onOpenProcess` first with the attached
target PID (`memory.pid` as a Lua number, always available at the
bootstrap call site), then `onTableLoad` with the Lua literal
`false` (documented bounded deviation: the once-per-attach
bootstrap has no before-load phase, so the callback only ever sees
`false`). Each callback runs inside one pcall-wrapped dispatch
chunk with the argument injected as a literal (the PID as an int
literal — no string injection; the chunk itself uses only stdlib
`rawget`/`type`/`pcall`/`tostring`, so no table-scope allowlist
change is needed and callbacks may call the already-admitted
item-C APIs); result handling: `'absent'` (missing or present but
not a function) dispatches nothing and logs nothing, `'ok'` logs
`table-callback`, `'error: <msg>'` logs `table-callback-error`
with the callback name and the pcall error text (corpus shape: the
table-local `getTable` helper indexing the nil `mForm` — the pcall
error contains `attempt to index a nil value`); a throwing callback
is contained, `plan["table_lua"]` stays byte-identical (executed
True, empty reasons — the clean bootstrap stays clean for the
dependent record scripts), the second callback still dispatches,
and the attach continues unblocked (a Python-level host failure
logs `table-callback-error` fail-soft). The dispatch is idempotent
by construction (one clean bootstrap per confirmed attach with a
fresh host; re-attach re-fires on the fresh scope) with no extra
flag; refused or failed bootstraps retire the scope and skip the
dispatch. Tests: new
`tests/test_native_rt5_table_callbacks.py` +9 (CE order + arguments
pinned through the table-scope host read-back, the item-C
game-facing chain `getProcessList()[processId]` -> process name ->
`getProcessIDFromProcessName` back to the PID, throwing-callback
containment with exact meta byte-identity, absent and non-function
(`onOpenProcess = 42`) with zero `table-callback*` events,
idempotent across polls, re-attach re-fire, the C2 dynamic
addresslist surface usable from a callback, onTableLoad only ever
false, refused bootstrap skips the dispatch). Full main suite after
the merge **3,826 OK / 25 expected skips** (baseline 3,817).
Catalog remeasure (run `blocked-catalog-rt5d-main`): **zero delta**
vs
`blocked-catalog-rt5c2-main` (151/151 load, 117,634 total, 116,581
supported (60,161 staged), 1,053 blocked, 0 compile errors, 0 newly
blocked, 0 reason-changed) — the dispatch is runtime host behavior
and the catalog is static plan-level. `runtime_unverified` remains:
the callback answers are untested on a live target.

Update (2026-10-31, RT-5 item B): the table-level `<CheatCodes>`
code-list plan path landed (lane `native-0.20-rt5-b`, commit
`3f1cce3`, merged to `main` as `9ef4a74`): fail-closed per-entry
parse — each `<CodeEntry>` with a non-hex or odd-length byte capture,
an empty `<Actual>`, a missing `<Description>`, or no usable address
is dropped with a named warning while the table still compiles; the
section is bounded at `MAX_CODE_PATCH_ENTRIES = 4096` (an oversized
section is ignored whole); `GroupHeader="1"` rows become supported
`heading` records (the corpus carries zero of them; CE group
activation is not executed). Byte-capture codec: `<Byte>`
child-element sequences joined, whitespace-stripped element-text
fallback, whole-byte (even-length) gate, lowercase normalization,
empty = absent capture. Plan projection: kind `code_patch`, synthetic
IDs at `CODE_PATCH_ID_BASE = 2**32` in table order — the RT-5 C2
dynamic-record journal owns [2**31+1, 2**31+4096] as session-scoped
IDs, so the two synthetic ID spaces can never collide (documented
deviation from the task's 2**31 base); address composition mirrors
the CE code-list forms (`AddressString` verbatim, else `ModuleName`
+ normalized offset, else absolute hex uppercased), with a
compile-time static symbol-free expression gate
(`parse_expression` + `advanced_expression_symbols`, zero symbol
atoms) that blocks only the offending entry; `CheatCodes` is added
to the interpreted-section whitelist, so the load-time warning
disappears. Both plan validators re-derive the canonical shape
byte-exactly and refuse forged entries (low ID, uppercase/odd-length
hex, empty actual, oversized captures, symbol-carrying or unparseable
address, address/source mismatch, foreign executable metadata).
Engine lifecycle: enable verifies the live bytes against the
nonempty `<Before>` prefix (`code-patch-target-changed` named
refusal, zero writes), applies the `Actual` bytes — executable pages
through the verified coordinator hook journal, data pages through
the ordinary byte transaction — and journals `_Patch(address,
original, actual)` per patch; disable restores the original captured
at enable time (documented superset of CE, whose code list only ever
applies the `Actual` bytes) and refuses with
`code-patch-restore-mismatch` plus an engine block when the live
bytes diverge from both the captured original and the actual;
already-active entries are adopted with zero writes
(`code-patch-already-active`); wishes join the standard enabled-wish
store and re-enable after re-attach; close-time restore works through
the same path; `code_patch` entries are skipped in `_check_patches`
and render as switch rows with the `code` chip. Tests: new
`tests/test_native_rt5_code_patch.py` +26 (focused 26 OK). Full main
suite after the merge **3,880 OK / 26 expected skips** (baseline
3,854). Catalog remeasure on `main` (run
`blocked-catalog-020-rt5-be`, 2026-10-31): **117,634 -> 117,809
total, 116,581 -> 116,756 supported (+175 — every `CodeEntry` of the
22 tables now a supported `code_patch` record), 1,053 blocked
unchanged, 60,161 staged unchanged, 0 load errors, zero newly
blocked, zero reason changes** (per-table diff vs
`blocked-catalog-020-icons`: exactly the 22 CheatCodes tables gain
+175 supported rows). `runtime_unverified` remains: the code
patches' real-game effect is untested (AP-11 plane).

Update (2026-10-31, RT-5 item E): the `messageDialog` decision
landed on `main` (branch `native-0.20-rt5-be`, commit `a5d0a2f`,
merged as `b8bb4ee`): the hosted `messageDialog` / `MessageDialog`
is a **safe logged no-op** returning 0 (mbOK, truthy in Lua) with
the CE 7.5 argument shapes (message / title+message / dialogtype /
buttons); nil arguments are tolerated because corpus table Lua
passes undefined button constants as nil (CE `lua_tostring` /
`lua_tointeger` coercion); every call logs a `message-dialog`
debug event (title + message truncated, argument count); both
spellings are hosted in record scope and admitted in table scope
(`TABLE_LUA_READ_ONLY_NAMES`, 47 corpus table-Lua call sites).
Decision rationale: purely UI presentation — the safe no-op
preserves table flow for informational dialogs while a refusal
would break table Lua that continues after the call. Tests: new
`tests/test_native_rt5_message_dialog.py` +22 plus pin updates (the
SC2 table-load warning pin moves to the no-op behavior, the
process-info guard keeps the catch-all named refusal on a synthetic
name, the no-effect register docstrings note item E implemented).
Full main suite after the merge **3,902 OK / 26 expected skips**
(baseline 3,880). Catalog remeasure (run
`blocked-catalog-rt5e-iteme`, on the branch): **zero delta**
(151/151 load, 117,634 total, 116,581 supported (60,161 staged),
1,053 blocked, 0 load errors) — the no-op is runtime host behavior
and the catalog is static plan-level. With items B and E, **every
RT-5 inventory item (A, B, C, C2, D, E, F, G) has landed — RT-5 is
complete**; the next roadmap work is RT-6 (validation) and RT-7
(release gate).

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

Package status (2026-10-27): **RT-4.2 done** — catalog remeasure
`blocked-catalog-rt42-main`: **1,053 blocked** of 117,634 (net -298 over
the 1,351 state after the RT-4.3 merge: 298 unblocked — R4 Lua runtime
symbol providers 286 (now staged), R7 GetAsyncKeyState bare-call rows 12
(supported with the api_exports plan marker, link-time export
resolution), R3 keep-first scope fallback catalog-neutral — 0 newly
blocked, 28 rows reason-changed all still blocked and explained; detail
in the RT-4.2 update in the investigation queue). RT-4 is complete.
History: RT-4.3 (2026-10-26, remeasure `blocked-catalog-rt43-main`)
1,743 -> 1,351 of 117,634 (net -392: 392 unblocked, 0 newly blocked,
12 rows reason-changed all still blocked and explained); RT-4.5
(2026-10-24, remeasure `blocked-catalog-rt45main`)
1,778 -> 1,743 of 117,634 (net -35: RDR2 1, Resonance 1, SOTTR 2,
Shinkansen Sunless Sea 1, Subnautica_e67616 28, TheSinkingCity 2;
zero newly blocked; 7 rows reason-changed, all still blocked and
explained); RT-4.6 (2026-10-24, remeasure `blocked-catalog-rt46`)
1,807 -> 1,778 of 117,634 (net -29); RT-4.4 (2026-10-23, remeasure
`blocked-catalog-rt44`) 1,858 -> 1,807 of 117,634 (net -51: O6 30,
O7 8, O8 13); RT-3 (2026-10-23) cleared the one legacy-binary load
error (151/151 load, 1,858 blocked of 117,634); RT-4.1 (2026-10-22,
remeasure `blocked-catalog-rt41`) 2,698 -> 1,858 of 117,624 (net -840:
842 unblocked, 2 explained Cyberpunk shared-global regressions). The
user-requested trainer UI feature (Scripts view + row context menu
with script preview and entry assessment) landed on branch
`native-0.17-ui-script-inspector` 2026-10-24 (suite 3,587 OK /
25 expected skips; catalog remeasure `blocked-catalog-ui-scripts`
zero delta — UI-only change); per the user decision 2026-10-24 the
0.17 build is cut after the RT-4.2 merge. RT-4 is complete; the next
work is the RT-5 implementation items A-E per the inventory (roadmap
RT-5 row).

Suggested execution order: RT-4.1 (820, lowest risk and the largest
guaranteed delta) first, then RT-4.3 (452), RT-4.4 (65), RT-4.5 (57),
RT-4.6 (219), and RT-4.2 (1,085) last — its AA_HIDDEN portion cleared
progressively as the root packages landed, and the residual is runtime
provider work — done 2026-10-27 (remeasured 1,351 -> 1,053 blocked).
All six RT-4 packages are complete. Remeasure the catalog after each
package (roadmap rule).

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
