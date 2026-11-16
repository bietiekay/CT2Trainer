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

Class-d ratification (2026-11-12, Lane C, merged as `7d92482`): the 80
`BaseAddress` rows of R6 (five UE5 script-template tables x 16) are
blocked by design until the user imports the symbol; the test-only
lane `native-lane-c-baseaddress` proves the documented user-symbol
import path end-to-end - with a `<UserdefinedSymbols>` `BaseAddress`
entry the same rows are fully supported (not staged; static UDS
address, `requires=['BaseAddress']`), byte-exact through the engine,
and the as-is rows keep the exact named class-d block (the block
message names the remedy). Catalog zero delta `blocked-catalog-lane-c`
(vs `blocked-catalog-043-tgc`); the residual 3 rows (2
`MapLastLeftClickCoordinates_Pointer`, 1 `r15l`) are out of scope and
keep their original reasons. Full main suite 5,020 OK / 36 expected
skips after the merge.

Dynamic Lua symbol registration ratification (2026-11-12, Lane A,
merged as `ff6e8d6`): the 182 rows of the two dynamic
symbol-registration shapes of the 537-blocked census are proven and
staged - the Witcher3 returned-define shape (the ENABLE Lua returns a
`define(<ident>, <expr>)` string spliced into the AA section per the
CE contract, so the record's own envelope may reference the defined
symbol: the adopted idents leave `requires`, recorded in the
deterministic `lua_define_symbols` plan marker, expression position
only - a bare `name:` label keeps the program-owned contract) and the
GoW literal name-list shape (the bounded derivation of the
constant-string column registered through the exact `X[i][k]` indexed
call argument; the same register-and-release rule as the WP-14
extraction; >64 names stay unproven). Proven on the synthetic shapes
(plan adoption, the expression-position vs bare-label boundary,
forged-metadata refusal at both plan gates, byte-exact engine
roundtrip with the hosted registration surface). Catalog remeasure
`blocked-catalog-lane-a`: 117,809 total / 117,454 supported / 12,974
headings / 104,305 actionable / 355 blocked (-182 vs
`blocked-catalog-lane-c`, zero newly blocked, zero reason changes;
exactly the 3 Lane A tables changed, the other 148 byte-identical).
Each Witcher3 table keeps its single `createthread` RT-5G residual
(class c gate, O22). Full main suite 5,036 OK / 36 expected skips
after the merge.

Nested relative-address staging ratification (2026-11-12, Lane B,
merged as `285fb8a`): the 134 rows of the Octopath2
relative-address census - the last lead case of the 537-blocked
cycle - are proven and staged: the staging walk folds relative
ancestors with offset-carrying levels and index-times-stride own
literals (`+00*04`) through the deterministic synthetic symbol
`__ct2_rtbase_<anchor_id>` (plan metadata, never a dependency; the
engine injects the anchor heading's live base per activation call,
inert and named fail-closed while it is missing, a registered
symbol under the placeholder name the named collision); the
byte-stable flat signed-hex total is kept while every level is a
plain-hex relative literal with no pointer offsets anywhere (the
RT-4.3 O9/O1 form, unchanged - the Death Stranding 2 and The
Sinking City plan entries byte-identical against the pre-lane
main); intermediate headings are never staged and addressless
headings with pointer offsets keep the byte-for-byte ambiguous-base
refusal. Proven on the synthetic shapes (flat / nested / stride /
deep-chain plan folds, the placeholder proven out of the symbol
table, byte-exact engine resolution at analysis-derived
pointer-chain addresses, UDS collision, forged-marker refusal at
both plan gates, two-compile determinism). Catalog remeasure
`blocked-catalog-lane-b`: 117,809 total / 117,588 supported /
12,974 headings / 104,439 actionable / 221 blocked (-134 vs
`blocked-catalog-lane-a`, zero newly blocked, zero reason changes;
exactly the 1 Octopath2 table changed, 134 -> 0, the other 150
byte-identical). Full main suite 5,049 OK / 36 expected skips after
the merge. With Lane B all three lead cases of the 537-row census
(Lane A 182, Lane B 134, Lane C 80 by design) are closed; the
remaining 221 blocked rows are the documented design/gate residuals
(80 `BaseAddress` class-d by design, 79 required symbols not
defined in their table, 23 no-unique-supported-provider, 11
KeyHandlerThread WP-37, 6 RE2 AP-08.7, 4 usemono > 7.5, 2 + 2
relative-ancestor refusals kept by design, 2 createthread RT-5G, 1
pBase Cronos, 5 trailing-token, 6 single-row AA-syntax / DISABLE
re-init).

Trailing-offset parity ratification (2026-11-14, post-0.47 residual
lane, `main` @ `5d467dc`): the four fixable "Unexpected trailing
address expression tokens." rows of the 210-blocked post-0.47
census (qt-ds-1 + qt-ds-2, records 130674 + 130675: the value-record
addresses `[mats]20` / `[mats]28` next to their supported `[mats]`
/ `[mats]+8` / `[mats]+10` / `[mats]+18` siblings) are proven
against the CE 7.5 source: `TSymhandler.tokenize`
(symbolhandler.pas L3073-3140) splits `[mats]20` into the tokens
`[`, `mats`, `]`, `20`; the `]` pointer dereference (L5516-5553)
resolves the bracket range to the dereferenced hex value, and the
arithmetic accumulation (L5603-5655) computes each remaining
non-operator token with `StrToQWordEx('$'+token)` and adds it (`+`
is the default operation) - CE reads `[mats]20` as
`[mats]+0x20` (hex default), while the 0x/$/#-prefixed spellings
fail the arithmetic and a `(` after `]` enters CE's record-by-
description lookup path (L5461-5494, out of parity scope). The
bounded grammar extension in `address_expression.parse_expression`
gives one value atom directly after a `]` token an implicit `+`
operand unless it is an explicit operator, a closing/repeating
bracket, a `(` or a 0x/$/#-prefixed number; a `[` after `]` is
included (CE resolves both dereferences and adds their values).
Byte stability: no supported expression can contain `]` followed by
a value atom, so every supported address parses byte-identically.
Documented clean-room extension: `[[mats]20]` parses as the regular
`[[mats]+20]` (CE's nested digit-merge concatenates the hex
digits). The fifth census row (raymanlegends_dvt `Made by`, a
two-atom string address without a closing bracket) stays blocked by
design - authoring junk CE also fails. +19 tests
(`tests/test_native_trailing_offsets.py`). Catalog remeasure
`blocked-catalog-048-trailing`: 117,809 total / 117,603 supported /
12,974 headings / 104,454 actionable / 206 blocked (-4 vs the 0.47
baseline: exactly the four qt-ds rows unblocked, zero newly blocked,
zero reason changes, the other 149 tables byte-identical). Full main
suite 5,127 OK / 36 expected skips. Shipped as the 0.48 release.

0.48 release record (2026-11-14, run `native-20261114T133842Z-8ee6999f`
cut from `main` @ `5d467dc`): the CE 7.5 trailing-offset parity
ships as the 0.48 release - the compatibility lane against the
210-row post-0.47 catalog census: the four `[mats]20` /
`[mats]28` value-record rows of qt-ds-1 + qt-ds-2 (records
130674 + 130675 each, next to their supported `[mats]` /
`[mats]+8` / `[mats]+10` / `[mats]+18` siblings) are proven
against the CE 7.5 source and closed by the bounded grammar
extension in `address_expression.parse_expression` (one value
atom directly after a `]` token takes an implicit `+` operand
- the CE `TSymhandler` contract: symbolhandler.pas L3073-3140
tokenize, L5516-5553 `]` dereference, L5603-5655 arithmetic
accumulation with `+` as the default operation, hex default;
explicit operators, a closing/repeating bracket, a `(` and
0x/$/#-prefixed numbers stay refused; byte-stable: no
supported expression can contain `]` followed by a value
atom); the fifth census row (raymanlegends_dvt `Made by`, a
two-atom string address without a closing bracket) stays
blocked by design - authoring junk CE also fails; +19 tests,
in-build suite 5,127 OK / 36 expected skips, `ce_inputs: []`,
`runtime_unverified` deliberately kept per gate; the build
ran unsigned by default (no code-signing certificate on this
machine; `build.json` `code_signing`: converter / master
signed false, reason not-configured - the signed path
activates with a user-supplied trusted-CA PFX); source
ZIP `CT2Trainer-0.48-source.zip` sha256
`feb962e5628027f1ee79acbc16cb10a4dfe36ef5a3de7f4cf4f3681d9cc37f0b`
(14,682,168 bytes), portable ZIP
`CT2Trainer-0.48-windows-portable.zip` sha256
`352069d184e93f19f6ec56ce9236bedc168b09e66da7c3ac2af15b13615d3a85`
(49,879,644 bytes; the frozen `CT2Trainer-Master.exe`
sha256 `9843d6dce2445af3bc883f12b9b16f6b5eb2c0fbfa2c86dae986c77c65383f10`,
17,066,255 bytes, ships next to the converter). Catalog
remeasure `blocked-catalog-048-trailing`: 117,809 total /
117,603 supported / 12,974 headings / 104,454 actionable /
206 blocked (net -4 vs the 0.47 baseline: exactly the four
qt-ds rows unblocked, zero newly blocked, zero reason
changes, the other 149 tables byte-identical; the rayman row
stays blocked by design); the remaining 206 blocked rows are
the documented design / gate residuals and AP-11 stays open
by definition.

Shape-3 variable-symbol ratification (2026-11-14, post-0.48
residual lane, `main` @ `20c63c1`): the two fixable classes of
the 206-blocked post-0.48 census are closed. The 8 Fallout4
"Player Editor" stat rows (Fallout4.CT ids 946-952 + 956) are
the lead case of the shape-3 embedded-Lua symbol provider: a
record's `{$lua}` walks a runtime table and registers each
entry under its name through a variable that ranges over a
flat literal string array (`local pointers =
{"str","per","end","cha","int","agi","luck","xp"}`,
`local ptr = pointers[id]`, `unregisterSymbol(ptr)` /
`registerSymbol(ptr, i + 4, true)`). The bounded static
derivation in
`lua_symbol_providers.extract_lua_symbol_providers` (flat
string arrays only, string constants only, the exact
`local var = ARRAY[i]` single-index binding with a variable
index, one binding per variable, one array definition per
name, same part) makes the array's string constants the
record's staged provides; the table re-keying (`ARRAY[k] =
v`) changes no value and is ignored; out of bound (unproven,
dependents keep the named missing-provider block): row
tables, numeric or identifier cells, constant indices (the
full array would over-prove), double-index tails (the
shape-2 indirect form), re-bound variables, unbound arrays,
non-local bindings, call arguments, more than MAX_PROVIDERS
derived names - every shape pinned; registration evidence
from the preamble + enable lua parts, release evidence from
the disable phase only (the enable-phase
`unregisterSymbol(var)` is the re-entrance guard, not a
deactivation release); the strict-pair / one-shot adoption
rule and the MAX_PROVIDERS valve unchanged. The 17 residual
class-d value-symbol rows (roadmap class d: "probed: no
Delphi handling - user/Lua symbol") are ratified on the
documented `<UserdefinedSymbols>` import path in the tests-
only lane `tests/test_native_user_symbol_import_remaining.py`:
6 x `g_GameLibSystemAssets` (HorizonForbiddenWest, both file
instances carry the identical row shape), 5 x `HeroSystem`
(RiftApart), 3 x `pGrav` (YLILWin64), 2 x
`MapLastLeftClickCoordinates_Pointer` (AtomicHeart v1.2), and
the one Kena module-qualified operand
`Kena-Win64-Shipping.UResourcesComponent::FreeResources`
(decomposed by the dependency walk into three symbol parts -
FreeResources, Kena, Win64; the full managed name as a single
user symbol does NOT cover the decomposition, the progressive
remedy names the next missing part each time): every row
blocked as-is with the exact named class-d message, fully
supported (and NOT staged - the UDS address is static) and
free of record dependencies (the WP-46 UDS zero-candidate
fallback in `compiler._dependencies`) once the import
exists, resolved byte-exactly through the engine (the
flattened expression chains and the offset-list
`resolve_pointer` path). The 2 `HeroHealthVFTable` rows of
RiftApart (921 / 1030) stay out of scope: their
registration lives in an encoded embedded-Lua block
(`loadTableFiles` -> `findTableFile`, Ascii85 `<Files>`)
with a `createThread` entry point, not a static symbol
import. +28 tests (15 shape-3 in
`tests/test_native_lua_variable_symbol_providers.py` + 13
ratification). Catalog remeasure
`blocked-catalog-049-variable`: 117,809 total / 117,611
supported / 12,974 headings / 104,462 actionable / 198
blocked (net -8 vs `blocked-catalog-048-trailing`: exactly
the 8 Fallout4 "Player Editor" stat rows unblocked, zero
newly blocked, zero reason changes, the other 150 tables
byte-identical). Full main suite 5,155 OK / 36 expected
skips. Shipped as the 0.49 release.

0.49 release record (2026-11-14, run `native-20261114T184922Z-4b721a9e`
cut from `main` @ `20c63c1`): the FO4 "Player Editor"
shape-3 dynamic-variable Lua symbol provider + the remaining
class-d user-symbol import ratification ship as the 0.49
release - shape 3 in
`lua_symbol_providers.extract_lua_symbol_providers` (a
record's `{$lua}` registers each entry under its name
through a variable that ranges over a flat literal string
array - the array's string constants are the record's
staged provides; strictly bounded: flat string arrays only,
the exact `local var = ARRAY[i]` single-index binding with
a variable index, one binding per variable, one array
definition per name, same part; out of bound: row tables,
numeric or identifier cells, constant indices, double-index
tails, re-bound variables, unbound arrays, non-local
bindings, call arguments, more than MAX_PROVIDERS derived
names - every shape pinned; registration evidence from
preamble + enable lua parts, release from the disable phase
only) closes the 8 Fallout4 "Player Editor" stat rows, and
the tests-only ratification lane
(`tests/test_native_user_symbol_import_remaining.py`) proves
the documented `<UserdefinedSymbols>` import path on the 17
residual class-d value-symbol rows (6
`g_GameLibSystemAssets` / 5 `HeroSystem` / 3 `pGrav` / 2
`MapLastLeftClickCoordinates_Pointer` / 1 Kena three-part
`FreeResources` + `Kena` + `Win64` module-qualified operand):
blocked as-is with the exact named message, supported /
unstaged / dependency-free with the import, byte-exact
through the engine; the 2 `HeroHealthVFTable` rows stay out
of scope (encoded embedded-Lua registration with a
`createThread` entry point, not a static symbol import);
+28 tests, in-build suite 5,155 OK / 36 expected skips,
`ce_inputs: []`, `runtime_unverified` deliberately kept per
gate; the build ran unsigned by default (no code-signing
certificate on this machine; `build.json`
`code_signing`: converter / master signed false, reason
not-configured - the signed path activates with a
user-supplied trusted-CA PFX); source ZIP
`CT2Trainer-0.49-source.zip` sha256
`e2adfb4d6153d0293e1be70e43d15f71a5b8ecd6889b7ecb74ec79cc9179ce24`
(14,699,553 bytes), portable ZIP
`CT2Trainer-0.49-windows-portable.zip` sha256
`4139bf2079f11ca7fba8c41b1d0c1bd201d146abdd3f8171bbafa18a7a931675`
(49,888,023 bytes; the frozen `CT2Trainer-Master.exe`
sha256 `d3ada53a7ebc6c160be55608046a286ba98028a1858cc2d950a64327a529d63b`,
17,070,681 bytes, ships next to the converter). Catalog
remeasure `blocked-catalog-049-variable`: 117,809 total /
117,611 supported / 12,974 headings / 104,462 actionable /
198 blocked (net -8 vs the 0.48 baseline: exactly the 8
Fallout4 "Player Editor" stat rows unblocked, zero newly
blocked, zero reason changes, the other 150 tables
byte-identical; the 17 class-d rows stay blocked by design
until the user imports the symbols); the remaining 198
blocked rows are the documented design / gate residuals
(80 `BaseAddress` by design until the documented user
import, 28 DS2 encoded-Lua + 15 CatValues out of scope, 17
class-d value-symbol rows ratified by the 0.49 import-
ratification lane, 2 HeroHealthVFTable out of scope, 21
no-unique-supported-provider, 11 KeyHandlerThread WP-37
external ownership, 6 RE2 AP-08.7 custom value types, 4
usemono > 7.5 out of parity scope, 2 + 2 relative-ancestor
refusals kept by design, 2 createthread / threadWait RT-5G,
1 pBase Cronos, 1 trailing-token (the rayman `Made by` row,
by design), 6 single-row named AA-syntax / DISABLE re-init
refusals) and AP-11 stays open by definition.
Provider-21 parity lane (2026-11-14, post-0.49 residual lane,
main @ `4f747ce`): the 21 "no unique supported provider" rows of
the 198-blocked post-0.49 census are closed - 5 unblocked by two
CE 7.5 source parity fixes, the 17 remaining rows ratified as
blocked by design. Fix 1 - comment-to-EOF: an unterminated
`{ ... }` or `/* ... */` block comment is stripped silently to
the end of the source (CE `removecomments`, autoassembler.pas
L732-798, read-only reference: comment state persists to the
end of the text, no error path) in `aa_program._clean_source`
and `aa._without_comments`; the quoted-string refusal stays; a
comment that swallows a section marker removes that section
(named section refusal). Unblocks SonicFrontiers 1337230409
"Pin Ball" (valid program + trailing unterminated brace
comment) + dependents 1337230410 "Score" / 1337230411 "Lives".
Fix 2 - shared-globalalloc: a compatible duplicate provider
set (every declarer allocates the same shared global with the
same size and flags,
`global_alloc.shared_provider_compatible`) collapses
keep-first in `compiler._dependencies` instead of the
ambiguity refusal - CE `globalalloc` (autoassembler.pas
L2103-2148) reuses the existing same-process allocation by
name (symbolhandler.pas L3713+ `SetUserdefinedSymbolAllocSize`
lookup-first) and `GlobalPool.acquire` keeps the name-keyed
exact-flag contract, so every compatible declarer resolves to
the identical address; the keep-first scope
(`provider_alternatives`) covers the compatible sets, so the
RT-4.2 (R3) fallback reaches them too; the "Unselected symbol
provider conflicts" branch stays reachable only for full sets
the compatibility check rejects. Unblocks Cyberpunk2077 380/381
(`weaponPtr` dependents - the two rows RT-4.1 had documented
as the "pinned shared-global contract" regressions). Catalog
remeasure `blocked-catalog-050-provider21`: 117,616 supported
/ 193 blocked (net -5 vs `blocked-catalog-049-variable`:
exactly the 5 rows above, zero newly blocked, zero reason
changes, the other 148 tables byte-identical). The
ratification lane
(`tests/test_native_provider21_ratification.py`, 14 tests, 7
clusters, synthetic fixtures mirroring the real-table shapes)
pins the 17 remaining rows as blocked by design - per cluster:
the provider's exact block reason, the dependents' exact
generic refusal, and the counter-proof that the rows resolve
once the documented condition is met (no hidden second gate):
Cronos `gun` x3 (WP-37 handover: the provider releases the
externally owned `pBase`), Cyberpunk `healthPtr` x4 (the
table's own `aobscanmodule(..., $proces, ...)` typo - CE fails
the same row: `getmodulebyname` misses,
`getAddressFromName` fallback misses, the aobscanmodule
handler aborts with rsAAModuleNotFound, autoassembler.pas
L1073-1145, no `$proces` special case anywhere in CE), DS2
`KeyHandlerThread` x3 (the Lua providers' static AA envelope
releases the externally owned symbol - the prefixed
handover), DS2 `freecam_enabled` (provider references the
nowhere-registered `g_Instance` - the actionable per-symbol
report), DS2 `InventoryItemProperties_call_dest` (bare call
target in the table source only - the generic wording, not the
missing-definition report), ForgottonAnne usemono x3 (out of
parity scope by design: targets a CE newer than 7.5),
RiftApart `HeroHealthVFTable` x2 (rows 1031 / 1032, provider
1030 "Modify Damage Packet" - the encoded embedded-Lua
registration with a `createThread` entry point is out of
scope, RT-5G; the documented static-import remedy is the
counter-proof). +16 tests; full main suite 5,171 OK / 36
expected skips. Shipped as the 0.50 release.

0.50 release record (2026-11-14, run `native-20261114T223759Z-086989d6`
cut from `main` @ `4f747ce`): the Provider-21 parity lane
ships as the 0.50 release - the CE 7.5 comment-to-EOF parity
in the AA source scanners (unblocks the SonicFrontiers "Pin
Ball" provider + its 2 dependents) and the CE 7.5 shared-
globalalloc parity in the keep-first collapse (unblocks the 2
Cyberpunk2077 `weaponPtr` dependents), plus the tests-only
ratification of the 17 by-design rows of the 21-row "no
unique supported provider" census (exact provider block
reason + exact dependent refusal + counter-proof per
cluster); catalog remeasure
`blocked-catalog-050-provider21`: 117,616 supported / 193
blocked (net -5, zero newly blocked, zero reason changes, the
other 148 tables byte-identical); full main suite 5,171 OK /
36 expected skips; in-build suite 5,171 OK / 36 expected
skips, `ce_inputs: []`, `runtime_unverified` deliberately kept
per gate; the build ran unsigned by default (no code-signing
certificate on this machine; `build.json` `code_signing`:
converter / master signed false, reason not-configured - the
signed path activates with a user-supplied trusted-CA PFX);
source ZIP `CT2Trainer-0.50-source.zip` sha256
`79c841e9bd7978fdc954a783f7f6989b79d82da9d10a95c35e66a20b7ee6520b`
(14,709,622 bytes), portable ZIP
`CT2Trainer-0.50-windows-portable.zip` sha256
`fc89315877b0c60b53db8bde568e0c751002f0912e9ad1726f6373eb50f59187`
(49,891,552 bytes; the frozen `CT2Trainer-Master.exe`
sha256 `417708d985bfb0f84530b0fe3703aa7788db81e10e48915218fc875cf236aab6`,
17,071,577 bytes, ships next to the converter).

Residual-census ratification lane (2026-11-15, post-0.50 residual
lane, main @ `35542f4`): the five remaining unrated residual
classes of the 193-row `blocked-catalog-050-provider21` census are
pinned as blocked by design - every other residual row is already
covered by a documented gate or by a 0.44-0.50 ratification lane.
`tests/test_native_residual_ratification.py` (13 tests, 6 clusters,
synthetic fixtures mirroring the real-table shapes, no real-table
path references) pins, per cluster, the exact block reason as
measured in the census + the counter-proof that the rows resolve
once the documented condition is met (no hidden second gate): DS2
`KeyHandlerThread` x11 (every record allocates the SAME symbol name
through a Lua-generated `alloc` line and registers / releases it in
the static `{$asm}` envelope; the static program never lists the
Lua-generated allocation, so each record's own `dealloc` drops to
`unowned_cleanup_dropped` and the 0.42 cleanup-parity re-check
re-blocks each record with the prefixed WP-37 handover refusal,
owner = first other entry in entry order; CE 7.5 breaks the same
way at runtime - the later record's `registersymbol` overwrites the
shared name, so the earlier record's disable-phase `dealloc` frees
the later record's live thread block: the table is a
one-record-at-a-time test harness), AtomicHeart-Win64-Shipping 73
(the glued `unregistersymbol(energyBkp)dealloc(newmem)` DISABLE line -
CE consumes the line at the first directive and silently discards
the glued dealloc: a leaked block, the record works), P3R-v4 229
(`reassemble(moneylost_gain+4,5)` - CE reassemble is
single-argument), Cyberpunk2077 159 (`assert(true)` - CE assert
requires the two-argument `assert(address, bytestring)` form),
TheSinkingCity Remastered 258084 (the changed DISABLE
re-initialization of the record's own global - the O19
shared-global contract fails closed by design), Little Kitty, Big
City 1 / 2 (`usemono()` in the Static AA envelope prefix - targets
a CE newer than 7.5, out of parity scope). Tests only, zero catalog
delta; full main suite 5,184 OK / 36 expected skips; remeasure
`blocked-catalog-051-residual`: zero delta (117,809 total /
117,616 supported / 12,974 headings / 104,467 actionable / 193
blocked - record-level diff: 0 count diffs, 0 newly blocked, 0
unblocked, 0 reason changes, all 151 tables byte-identical). The
remaining 193 blocked rows are the documented design / gate
residuals (80 `BaseAddress` by design until the documented user
import, 28 DS2 encoded-Lua + 15 CatValues out of scope, 17 class-d
value-symbol rows ratified by the 0.49 lane, 2 HeroHealthVFTable
out of scope, 17 no-unique-supported-provider rows ratified by the
0.50 lane, 11 KeyHandlerThread WP-37 external ownership ratified by
this lane, 6 RE2 AP-08.7 custom value types, 4 usemono > 7.5 out of
parity scope (ForgottonAnne x2 by the 0.50 lane + Little Kitty x2
by this lane), 2 + 2 relative-ancestor refusals kept by design,
2 createthread / threadWait RT-5G, 1 pBase Cronos, 1 trailing-token
(the rayman `Made by` row, by design), 5 single-row named
AA-syntax / DISABLE re-init refusals (AtomicHeart 73 /
Cyberpunk2077 159 / P3R-v4 229 / TheSinkingCity 258084 ratified by
this lane; the Cyberpunk2077 259 `$proces` typo row by the 0.50
lane) and AP-11 stays open by definition. Shipped as the 0.51
release.

0.51 release record (2026-11-15, run `native-20261115T023110Z-4ed2835e`
cut from `main` @ `35542f4`): the post-0.50 residual-census
ratification lane ships as the 0.51 release - tests only, zero
catalog delta (the five remaining unrated residual classes of the
193-row census pinned as blocked by design with counter-proofs;
see the lane paragraph above); catalog remeasure
`blocked-catalog-051-residual`: 117,616 supported / 193 blocked
(zero delta vs `blocked-catalog-050-provider21`: record-level diff
per table - zero count diffs, zero newly blocked, zero unblocked,
zero reason changes, all 151 tables byte-identical); full main
suite 5,184 OK / 36 expected skips; in-build suite 5,184 OK / 36
expected skips, `ce_inputs: []`, `runtime_unverified` deliberately
kept per gate; the build ran unsigned by default (no code-signing
certificate on this machine; `build.json` `code_signing`:
converter / master signed false, reason not-configured - the
signed path activates with a user-supplied trusted-CA PFX); source
ZIP `CT2Trainer-0.51-source.zip` sha256
`a1cc1b3eb33aca8ff7a041d999f5714a84aec238e782f396f5e6eb7385d4f525`
(14,717,423 bytes), portable ZIP
`CT2Trainer-0.51-windows-portable.zip` sha256
`53923298adf229d526995274c98f3bd7476d124ca2d0fc13577392571395a675`
(49,894,393 bytes; the frozen `CT2Trainer-Master.exe`
sha256 `1dff59f006370da718ecf343e66d6cdf78ad7b462bb7468348a4dbbdeb5893bb`,
17,071,049 bytes, ships next to the converter).

Windows fixture runtime evidence (2026-11-15, RT-6 fixture-owned
portion, on the 0.51 build, repo `main` @ `9e5e906`, clean tree):
the first Windows function gate was verified on
`Microsoft Windows NT 10.0.26300.0` x64 with MSVC `cl` 19.44.35229
(BuildTools 2022) - preflight run `20261115T035818Z-ed5ba8bd`
passed (owned `FixtureTarget.exe` sha256
`b6a5c45ced721d345790a45d359747dfb7e69d28bea0dd6d2ea767e1e0d49086`,
PE `0x8664`, single marker, baseline `value=1234` / `pause=0`); the
frozen generated trainer (0.51 template, `FixtureTrainer.exe` sha256
`38afb9790d3fb0f74bfb87b03707cda81d69187927207ae5e0834c5e0dd533bc`)
ran the owned fixture gate against a live target it spawned itself -
report `ct2trainer-fixture/v1` `passed`, `frozen_runtime: true`,
`ce_runtime_used: false`, 14/14 observations (attach + AOB, value
4321, Lua record write 5432, Lua worker, memscan + foundlist,
keyboard/controller API, NASM/iced encoding, freeze, pause patch,
concurrent-trainer blocked, resume, saved-switch persistence across
target restart, trainer restart, close restore + lock release).
This is fixture-owned runtime evidence only: pinned-game-build
observation, the clean-machine protocol and the Deck / Proton /
touch protocol remain open per the RT-6 acceptance, so
`runtime_unverified` stays set. Records:
`tests/windows/fixture_target/README.md` ("Verified direct check
(2026-11-15, 0.51)"), `documentation/native-verification.md`,
ledger section in `documentation/native-progress.md`.

Windows scan fixture runtime evidence (2026-11-15, RT-6
fixture-owned portion, source runtime, repo `main` @ `26e6ebc`
(the 0.52 content) on Windows NT 10.0.26300.0 x64, MSVC `cl`
19.44.35229 BuildTools 2022): the owned process/nth scan gate
documented in `tests/windows/scan_fixture/README.md` was
verified - the fixture was rebuilt from the unchanged source
(`scan_target.c` sha256
`4c939ab3c42aeea7eb2211253af8f7bbb374646afd12d744d06685bb7b72808f`,
single git commit `b6c48cc`; the CT unchanged at sha256
`440a5bf3fdaaae5e2756eed16f8728efd3c65c7c40084e2a0685f2e2c83366db`)
into run `native-scan-fixture-20261115T043627Z-cfea6da9`
(`verification.json` passed, `ce_inputs: []`; x64 target sha256
`e54b12801564aed37ad9ee3ed3283459e53f9f69ee8042af73730fc0784c5315`,
x86 target sha256
`d66756a12c741caf163823a26643bce5c0a0369c8b689fc00f0a3f52fa8a626e`;
`scan_probe.py` re-pinned to the fresh hashes). The first gate
run failed the open luacall gate fail-closed (`no luacall
binding factory`, before any allocation or write); the new
owned luacall binding
(`src/ct2trainer/native/luacall_binding.py` - `OwnedNthAobPort`
on the engine's attached target memory, module-bounded /
1-based occurrence / identity-checked / read-only;
`OwnedLuaCallBinding` covering exactly `lua_aobscan` /
`ct2trainerNthAOB`; `owned_luacall_binding_factory` wired at
the trainer / Master / scan-probe construction sites, engine
default stays fail-closed, plans naming any other Lua function
stay refused by exact name - the generic table-Lua route
remains open, AP-11) closed it. Re-run through the
source-runtime launcher (0.51 in-build venv python, exit 0):
both the x64 and x86 reports `ct2trainer-owned-scan/v1`
`passed`, `frozen_runtime: false`, `ce_inputs: []`,
`owned_markers_absent: true`, 8/8 checks each (exact-arch
target + three module patterns + private buffer, compact
process scan + real-held publication + independent readback,
nth module source adapter confirmed + journaled, earlier new
match does not rebind disable + both scopes restore exactly,
fresh reactivation rescans + saves the current occurrence,
target restart reapplies the confirmed wishes, controller
restart restores the saved confirmed records, final off +
normal target cleanup; terminal receipts in schema-valid
terminal states - 1 `target-exited` + 3 `abandoned`). This is
fixture-owned runtime evidence only: pinned-game-build
observation, the clean-machine protocol and the Deck / Proton
/ touch protocol remain open per the RT-6 acceptance, so
`runtime_unverified` stays set. The frozen scan gate (the
generated `ScanTrainer.exe`, `frozen_runtime: true`) was
re-run at the 0.52 build cut. Records:
`tests/windows/scan_fixture/README.md` ("Verified scan gate
(2026-11-15, source runtime)"), `documentation/native-verification.md`,
ledger section in `documentation/native-progress.md`.

0.52.1 release record (2026-11-15, run
`native-20261115T181026Z-00f5dfe8` cut from `main` @
`dc138e0`): the global-gate frozen-trainer launcher pair +
the string-fixture re-pin + the release allowlist fix ship
as the 0.52.1 release - the
`--global-fixture-target` / `--global-fixture-report` pair in
`launcher.py` in the house pattern (pairs entry, the
report-without-target orphan check, the single-mode dispatch
after the lua dispatch; the global gate has no string-style
plan-load failure reservation - an orphan flag or a mixed
gate is refused before the plan is read, exit 2, a frozen
embedded-plan failure is exit 2 without reserving a report,
the report itself reserved by `global_probe.run_probe` after
the fixture-plan validation) + the 6-test
`tests/test_native_global_launcher.py` + the release
allowlist fix in `tools/native_build.py` (the two global
gate CTs + `tests/windows/global_fixture` join the source
ZIP allowlist - the global gate was the only owned gate
whose fixture inputs were missing while the shipped
`test_native_global_probe.py` compiles the CTs) + the
string-fixture re-pin (the pin build had been cleaned
before the cut; rebuild
`native-string-fixture-20261115T174324Z-45f4` from the
unchanged source, MSVC `cl` 19.44.35229,
`string_probe.py` `TARGET_SHA256` x64
`7b815ff5148180b434a7ebe543411b54e4d5ce90399ed83e4bf8ecc5f77eb0fd`
/ x86
`7876bf70a8feab52a5774802708d82f1eab36f435231ba3045c59a7b7a7f0668`,
both pinned CTs + the plan fingerprints unchanged - no
compiler drift; both string gates re-verified 14/14 in the
source runtime); catalog unchanged
(`blocked-catalog-luacall-binding`): 117,616 supported /
193 blocked (zero delta vs the 0.52 baseline - this cycle
touches no table-parsing path); full main suite 5,203 OK /
36 expected skips (5,197 + 6); in-build suite 5,203 OK /
36 expected skips, `ce_inputs: []`, `runtime_unverified`
deliberately kept per gate; the build ran unsigned by
default (no code-signing certificate on this machine;
`build.json` `code_signing`: converter / master signed
false, reason not-configured - the signed path activates
with a user-supplied trusted-CA PFX); source ZIP
`CT2Trainer-0.52.1-source.zip` sha256
`c65883bf5a5161a0e4846ba4ed9a5c1725678ec363b94728f4d1dbbe603723a6`
(14,763,924 bytes), portable ZIP
`CT2Trainer-0.52.1-windows-portable.zip` sha256
`35b43cc56da28fc29b7663ee3efb61a953f4b085496176b21016365a1f26056e`
(49,918,368 bytes; the frozen `CT2Trainer-Master.exe`
sha256 `bd0388cbe45b350ee11117b99e55262ade6906e81e72e28c286fa1e3ddfe8316`,
17,074,203 bytes, ships next to the converter); the frozen
re-runs of the string (x64 + x86), x86 debug-hook, hook +
Lua-record and global (x64 + x86) gates re-ran at the
release cut on the 0.52.1 template stub (sha256
`df004f1afeea2d73fffe1747bb24e8139318311ac59893ea65759a9bf365e040`)
- the seven frozen trainers regenerated from the gate-passed
plans, every report status `passed` with
`frozen_runtime: true` (string x64 trainer sha256
`7943372c45f2521b93f65ecbe952ef387efa3612e4907b51fa899291e4120bcc`
14/14, string x86 trainer sha256
`e225c9adc45997a820ef0871341a087d1a0c5b885c645c4954e6a7f7e5d238b5`
14/14, x86 debug-hook trainer sha256
`425e81bf49743a09c91df76f5283dda60c89cb844d59a918c0abaf4231bb1813`
6/6, hook trainer sha256
`272f3c755970baf1259e75f98e6ee16c5a16eb6e613b4f4d6692fc16cf96e944`
7/7, Lua-record trainer sha256
`65d2ce70da27281e94b6a9ccbfc2668be2f499922e44437d3351ca8020653c70`
4/4, global x64 trainer sha256
`a96d407911a4223a5d93fc4f706e6c0820ac15674f343bda71d019736e31030e`
14/14, global x86 trainer sha256
`eef0cea97a3f2666df340a6e80981a2b6a8492c37092007df2c504c5fe09e683`
14/14; x86 / hook / Lua-record plan identity identical to
the source runtime; trainers + reports under the
git-ignored `build\windows-fixture\frozen-check-20261115T183206Z\`;
see the "Verified frozen ..." records in the string / x86
debug-hook / hook / global fixture READMEs).

Windows code-patch fixture runtime evidence (2026-11-16, RT-6
fixture-owned portion, source runtime, repo `main` @ `a4e805d`
(post-0.52.1; the code-patch lane is uncommitted at
measurement time) on Windows NT 10.0.26300.0 x64, MSVC `cl`
19.44.35229 BuildTools 2022): the 9th Windows function gate
(house pattern per `global_probe.py`) - the owned code-patch
fixture `tests/windows/codepatch_fixture/codepatch_target.c`
(sha256
`89f1bef4b4f59fbd6653bd9eb1ff6777d321c740bde30d2741f7af56fe7a52e9`,
7,679 B; recipe
`Invoke-CodePatchFixtureBuild.ps1` sha256
`27f627e804c33f8214f3a6203ee90c75dad67dfa493c23224019413f7ef1c27d`)
built for x64 + x86 into run
`native-codepatch-fixture-20261116T032022Z-bdd3` (`build.json`
schema `ct2trainer-owned-codepatch-build/v1` status `passed`,
`ce_inputs: []`; x64 EXE sha256
`3f217da553159221216db43c6c8e83481d5da2869edcdf68ca4f66980a9b891f`
147,456 B / x86 EXE sha256
`288855467feab361c2d27a64a4ff68bb73687923d8e3984003a3c7fe77ae6a85`),
the two pinned CTs `tests/fixtures/codepatch/` (four
`<CodeEntry>` `code_patch` records each, zero blocks /
warnings; x64 CT sha256
`3219ee42a0cab3f40a66fce762c62c6e0b49140e91fcff671759e8354d78bc31`,
x64 plan file sha256
`cef82a71b2cf082a7764f0fd203a47634106468001f3a0eee5496e1dde9360c8`,
x86 plan fingerprint
`c67846921cafeedb36387e465efa88fdaa95e80c7526bc485df817b8d6a28061`)
and the new pure gate `src/ct2trainer/native/codepatch_probe.py`
(report schema `ct2trainer-owned-codepatch/v1`) + the
`--codepatch-fixture-target` / `--codepatch-fixture-report`
launcher pair in `launcher.py` (orphan flag or a mixed gate
refused before the plan is read, exit 2; the report reserved
by `run_probe`). The gate exercises the full RT-5 item B
`code_patch` record lifecycle against a live owned target -
external-writer simulation through the target's own protocol
(`setdata A|B <hex>`), effects re-proven by the independent
`ProcessMemory` reader. Re-run through the source-runtime
launcher (exit 0; plan + report under
`build\windows-fixture\codepatch-check-20261116T082357Z\`):
the x64 report `ct2trainer-owned-codepatch/v1` `passed`,
`source_runtime: true`, `frozen_runtime: false`,
`ce_implementation_inputs: []`, `owned_markers_absent: true`,
14/14 checks (exact-child-image identity + module metadata;
baseline sentinels; data enable publishes the Actual bytes
and captures the original; the overlapping record is refused
with zero writes; data disable restores the captured
original; the target-changed enable is refused with zero
writes; the already-active state is adopted without a write
and the no-write disable leaves the dirty bytes in place; the
executable enable patches the live entry and the target's own
protocol executes it with exactly one hook journal; the
restore mismatch keeps the record applied and blocks the
engine; the blocked engine refuses actions and a second
controller's live state claim; target exit finalizes the
blocked session through `close-after-blocked` (journal
unlinked on identity-confirmed exit, `state.lock` /
`session.json` released, both saved wishes persisted); the
saved-ON replay on a fresh identity re-applies both routes;
the replayed disables restore the exact originals and retain
the `retired` terminal receipt; the normal close after exit
confirms cleanup) plus the dedicated recorded live-close
fence (a blocked live close on a third owned target refuses
with a `False` return and the exact
"code-patch-restore-mismatch" reason, touches nothing in the
target and preserves `state.lock` / `session.json` /
`state.json` / the `enabled`-state executable journal across
the target exit). The x86 source-runtime run is
**machine-gated pending**: the fresh unsigned x86 target
fails process creation with WinError 740 on this machine -
a name + architecture launch-block heuristic, not a
first-launch review of this specific binary: any x86
executable with a "patch"-like name is refused regardless of
content, path, parent or caller context (the x86 gate target,
a different x86 binary under the same name and the codepatch
/ mypatch / patchtool probes are refused while x64 binaries
with the same names, x86 with clean names and "dispatch"
launch fine); the Smart App Control first-launch hypothesis
is refuted (SAC registry state off / never enabled, no SAC
operations log, no block events, the user's prompt approval
did not clear the block) and AppLocker / WDAC / SRP are
absent or empty, no MOTW, no elevation manifest, no
third-party AV/EDR - the x86 pins are static-verified (target
hash, PE machine via the independent bounded header re-check,
plan fingerprint, RVAs cross-proven byte-exact against the
x64 runtime metadata) and the engine semantics are
architecture-neutral; the x86 run is recorded once the
machine's name + architecture block is cleared (user machine
action) or under the clean-machine protocol, together with
the frozen re-run (the generated trainers,
`frozen_runtime: true`) of both architectures at the next
release cut. This is fixture-owned runtime evidence only:
pinned-game-build observation, the clean-machine protocol and
the Deck / Proton / touch protocol remain open per the RT-6
acceptance, so `runtime_unverified` stays set. +24 tests
(`tests/test_native_codepatch_probe.py` 18 +
`tests/test_native_codepatch_launcher.py` 6); full main suite
5,227 OK / 36 expected skips; catalog unchanged at the
`blocked-catalog-luacall-binding` baseline (117,616
supported / 193 blocked - the lane touches no table-parsing
path; the release allowlist in `tools/native_build.py` gains
the two codepatch CTs + the
`tests/windows/codepatch_fixture` directory). Records:
`tests/windows/codepatch_fixture/README.md` ("Verified owned
code-patch gate (2026-11-16, source runtime, x64)"),
`documentation/native-verification.md`, ledger section in
`documentation/native-progress.md`.

0.52 release record (2026-11-15, run `native-20261115T070952Z-14405931`
cut from `main` @ `26e6ebc`): the owned luacall binding + the
Windows scan-fixture lane ship as the 0.52 release - the
production `luacall_binding_factory` behind the engine's
`_require_luacall_binding` gate (the owned reviewed nth-AOB
helper route for records whose AA envelope carries
`luaCall(...)` references; `luacall_binding.py` +
`tests/test_native_luacall_binding.py`, +13 tests; the scan
fixture re-pin run
`native-scan-fixture-20261115T043627Z-cfea6da9`; the scan
gate verified in the source runtime - the first run failed
the open luacall gate fail-closed, the new binding closed
it, both the x64 and x86 reports
`ct2trainer-owned-scan/v1` passed, 8/8 checks each; see the
scan-evidence paragraph above); catalog remeasure
`blocked-catalog-luacall-binding`: 117,616 supported / 193
blocked (zero delta vs `blocked-catalog-051-residual`:
record-level diff per table - zero count diffs, zero newly
blocked, zero unblocked, zero reason changes, all 151
tables byte-identical - the binding + wiring touch no
table-parsing path); full main suite 5,197 OK / 36
expected skips; in-build suite 5,197 OK / 36 expected
skips, `ce_inputs: []`, `runtime_unverified` deliberately
kept per gate; the build ran unsigned by default (no
code-signing certificate on this machine; `build.json`
`code_signing`: converter / master signed false, reason
not-configured - the signed path activates with a
user-supplied trusted-CA PFX); source ZIP
`CT2Trainer-0.52-source.zip` sha256
`4ab1445befb795a40387d6ab69b0bf7b5f333b73cd62d2769b3083cab6969a7b`
(14,729,777 bytes), portable ZIP
`CT2Trainer-0.52-windows-portable.zip` sha256
`2009c3f1a959766ab793c6b6b57d89dcfb27143b4b1a8c03b78665d450fbd2cf`
(49,899,983 bytes; the frozen `CT2Trainer-Master.exe`
sha256 `29f99e7a069a5a51d03b765ff40d8573684ba3567ec48f4f85fcc26722895903`,
17,072,825 bytes, ships next to the converter); the frozen
scan gate (the generated `ScanTrainer.exe`,
`frozen_runtime: true`) re-ran at the release cut on the
0.52 template - the two frozen scan trainers regenerated
with the new template stub (sha256
`23e8fed027b0e50f5bc1f81f7b7b626b6df951f5de8ba2a0e7c43fefbbf2d4a9`),
both reports `ct2trainer-owned-scan/v1` passed, 8/8 checks
each, `ce_inputs: []`, `owned_markers_absent: true`, plan
identity identical to the source runtime (frozen x64
trainer sha256
`283e50759750774bcd3c3b8c04020a58f87ac3ff94e4f74f233a28305d7745f5`,
frozen x86 trainer sha256
`8ebc01935a3bb70bfac6439c30c3f3ec8d540368426a8e79c189009a4703cb12`).

0.47 release record (2026-11-14, run `native-20261114T011046Z-ee5cecee`
cut from `main` @ `6e1940e`): the optional code signing for the
frozen and generated trainer executables (the Smart App
Control handling, the field block observed 2026-11-14 on the
0.46 trainer) ships as the 0.47 release - in-build suite
5,108 OK / 36 expected skips, `ce_inputs: []`,
`runtime_unverified` deliberately kept per gate; the build ran
unsigned by default (no code-signing certificate on this
machine; `build.json` `code_signing`: converter / master
signed false, reason not-configured - the signed path
activates with a user-supplied trusted-CA PFX, and a signed
build's certificate table is re-proven before publication);
source
ZIP `CT2Trainer-0.47-source.zip` sha256
`436a330aeceb70a51c2fc5585085a133b25ea6f05aedcdfa25353aa9042d436d`
(14,675,788 bytes), portable ZIP
`CT2Trainer-0.47-windows-portable.zip` sha256
`146ee9cd99a12865779ba1daff9e66fa0855be20a7a847d0bd47a513e74bc3a5`
(49,879,105 bytes; the frozen `CT2Trainer-Master.exe`
sha256 `a770f9689a5744a49aa26ec911437f0fcd09a05631e85edcfea92061b6658453`,
17,066,832 bytes, ships next to the converter). Catalog
unchanged at `blocked-catalog-046-regsize`: 117,809 total /
117,599 supported / 12,974 headings / 104,450 actionable /
210 blocked (no table-parsing path touched); the remaining
210 blocked rows are the documented design / gate residuals
and AP-11 stays open by definition.
0.46 release record (2026-11-13, run `native-20261113T185658Z-e543af1a`
cut from `main` @ `b348184`): the AA extended-register
`l` alias + `dqword` size-keyword parity ships as the
0.46 release (the compatibility lane against the
221-row post-0.44 census) - in-build suite 5,071 OK /
36 expected skips, `ce_inputs: []`,
`runtime_unverified` deliberately kept per gate; source
ZIP `CT2Trainer-0.46-source.zip` sha256
`c49323d56d8feab0652f676d86a739fb6204cff6ddeed8e4b326e43020ee4d62`
(14,661,247 bytes), portable ZIP
`CT2Trainer-0.46-windows-portable.zip` sha256
`1b130db71508e42b98c4127ebcec766bc79cd65aabdd563ed59d4b058bfc9fe9`
(49,857,331 bytes; the frozen `CT2Trainer-Master.exe`
sha256 `18306034231d6632ba15f4f23f62e611dd2c9b73e14db634d99f6cdccb7e8857`,
17,069,499 bytes, ships next to the converter). Catalog
remeasure `blocked-catalog-046-regsize`: 117,809 total /
117,599 supported / 12,974 headings / 104,450 actionable /
210 blocked (net -11 vs `blocked-catalog-lane-b`: the 9
direct register / size rows + 2 provider cascades
unblocked, zero newly blocked, zero reason changes); the
remaining 210 blocked rows are the documented
design / gate residuals and AP-11 stays open by
definition.
0.45 release record (2026-11-13, run
`native-20261113T144426Z-572d5b30` cut from `main` @ `58d6c8f`):
the per-session hotkey switch (MT-34) + the trainer-tick-sound
field fix ships as the 0.45 release - in-build suite 5,062 OK /
36 expected skips, `ce_inputs: []`,
`runtime_unverified` deliberately kept per gate; source ZIP
`CT2Trainer-0.45-source.zip` sha256
`3bdd783359623d273de15e90f4f0acc524d3ecbda64f925c3cf59de9d4e27416`
(14,657,388 bytes), portable ZIP
`CT2Trainer-0.45-windows-portable.zip` sha256
`58bac73098b219e3049668b55877e8a3e4fd758e6e1917b058da128e416eb4e2`
(49,854,120 bytes; the frozen `CT2Trainer-Master.exe` sha256
`f882add64b2fc0f9d66cb88ed2142684e71736de326b28f72ddb007186aa2d05`,
17,069,125 bytes, ships next to the converter). Catalog unchanged
at `blocked-catalog-lane-b` (117,588 supported / 221 blocked -
MT-34 and the sound fix touch no table-parsing path); the
remaining 221 blocked rows are the documented
design / gate residuals and AP-11 stays open by definition.
0.44 release record (2026-11-13, run
`native-20261112T233337Z-1dc678c6` cut from `main` @ `ab11893`):
the compatibility-lane cycle above ships as the 0.44 release -
in-build suite 5,049 OK / 36 expected skips, `ce_inputs: []`,
`runtime_unverified` deliberately kept per gate; source ZIP
`CT2Trainer-0.44-source.zip` sha256
`026886a700282a56c40568f30d2a4ebc57d6390a59cd59c42fd3f7f5dc8d49ff`
(14,648,668 bytes), portable ZIP
`CT2Trainer-0.44-windows-portable.zip` sha256
`656bf7106fd86a5a21532cf476b91f82cfafe2287ef5bf3d3ba41b6d2d9d6f36`
(49,885,729 bytes; the frozen `CT2Trainer-Master.exe` sha256
`02e4731ef30ce320f71594f37cb176402be64849a90656c785d474dbc50d6112`,
17,084,284 bytes, ships next to the converter). With 0.44 the full
deferred compatibility-lane cycle of the post-0.43 census is
released; the remaining 221 blocked rows are the documented
design / gate residuals and AP-11 stays open by definition.

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
   raymanlegends_dvt 1): resolved 2026-11-14 by the trailing-offset
   parity lane (0.48, `main` @ `5d467dc`) - the four `[mats]20` /
   `[mats]28` rows are CE 7.5 implicit-addition offsets (proven in
   symbolhandler.pas, see the trailing-offset ratification above)
   and are supported; the rayman `Made by` string address stays
   blocked by design (authoring junk CE also fails); counted under
   O4.
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
