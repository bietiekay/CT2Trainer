# CT2Trainer: Reference-Corpus Closure Plan (WP-19 … WP-42)

Status: **2026-10-13** — plan created at the start of the reference-corpus
closure cycle. Baseline: `main` @ `9a76eb8` (0.11), full suite 2710 OK /
25 expected skips, latest build `native-20261012T092729Z-2d8aaf12`.
Working branch for this cycle: **`native-0.12`** (cut from `main` before
the first integration).

Companion document: the consolidated gap assessment in
[`documentation/reference-gap-assessment.md`](../documentation/reference-gap-assessment.md)
(root causes, counts, CE 7.5 behavior-reference notes). This plan carries
the work packages, ownership, sequencing, test/fixture design, and the
compatibility-assessment update protocol.

## 1. Goal and completion criteria

Close the 21,852 blocked entries of the 151-table reference corpus
(local-only, never added to git) by implementing the missing engine
features and trainer/trainer-creator UX. Per work package (WP):

1. The implementing lane delivers a green full suite (baseline 2710/25 +
   new tests) in its own worktree, one commit.
2. The root agent merges, adds the anonymized derivative corpus case(s)
   (`TableReferences/case-NN.ct`), pins SHA-256 in
   `TableReferences/README.md`, and adds the case to
   `tools/corpus_denominator/__main__.py` (`PINNED`).
3. Root regenerates the deterministic measurement chain (feature matrix +
   AP-11 manifest) with one fresh run id, updates the pins in
   `tests/test_native_feature_matrix.py`, flips new/partial matrix rows
   to covered, and re-runs the **reference-corpus blocked catalog**
   (local tool; `blocked-catalog.json`) recording the per-reason-family
   before/after deltas.
4. Plan status row + `documentation/native-progress.md` updated in the
   same integration; working branch merged into `main` and pushed
   (normal merge, never force).

A WP is *done* only when its reason families drop to 0 **or** to a
documented, named residual (malformed authoring defects that stay
fail-closed), measured by the catalog re-run.

**Cycle completion (0.12):** all Wave 1 + Wave 2 WPs integrated; catalog
re-run shows the expected deltas; feature matrix rows for the new
capabilities flipped to covered with evidence; build re-cut from `main`.
Wave 3 (ownership handover, dynamic address provider, table-Lua
bootstrap, creator-UX, hotkeys) may continue on `native-0.12` or move to
`native-0.13` depending on evidence and risk; WP-42 (Forms rendering) is
explicitly deferred to a later milestone.

## 2. Corpus and reference-source rules

- Raw reference tables never enter the repository. The scratch corpus
  (`Temp\opencode\ref-corpus`) and the catalog outputs stay local-only.
- Derivative cases are independently authored synthetic tables: owned
  module token `ct2synthNN.exe` per case, neutral names, no game code,
  assets or strings; SHA-256 pinned in `TableReferences/README.md`.
- The CE 7.5 source (`C:\Users\xboxl\code\cheat-engine-7.5`) is a
  **behavior reference only** (2026-10-13 user decision): lanes may read
  it to understand CE behavior; **no code is copied or derived from
  it**. All implementations are clean-room; tests assert the documented
  target behavior, not CE internals.
- `reference-assessment/` (lane raw reports) stays gitignored.

## 3. Master work-package table

Unified numbering (lane proposals mapped: Lane B "WP-19..25" ≈ this
WP-19..23+25; Lane A WPs ≈ WP-24/27/32/33/34; Lane C WPs ≈ WP-28/29/30/
31/35/36/37; Lane D WPs ≈ WP-26/39/40/41/42).

| WP | Title | Main files | Unblocks (est.) | Wave | Parallel-safe with |
| --- | --- | --- | ---: | --- | --- |
| WP-19 | `$process` allowed in `validate_plan` | `compiler.py` | 20 (whole AtomicHeart table) | 1 | 20/21/24 (disjoint hunks), 22/23, 25, 26 |
| WP-20 | `@@` cursor in `global_alloc` + per-entry containment of `AddressExpressionError`/`GlobalError` | `global_alloc.py`, `compiler.py` (per-entry catch) | 349 (whole Cyberpunk table) | 1 | 19/21/24 (disjoint hunks), 22/23, 25, 26 |
| WP-21 | pointer-offset constant folding (+ annotated-hex normalization) | `compiler.py` (`_offsets`) | 216 | 1 | 19/20/24 (disjoint hunks), 22/23, 25, 26 |
| WP-22 | digit-leading module basenames | `address_expression.py` (`_TOKEN`) | 10 (whole 20XX table) | 1 | all |
| WP-23 | `::` managed-label alias | `address_expression.py` | ~15 | 1 | all |
| WP-24 | empty-value dropdown rows = non-writable separator metadata | `compiler.py` (`_dropdown`), `engine.py` (plan validation display model) | 10,894 | 1 | 19/20/21 (disjoint hunks), 22/23, 25, 26 |
| WP-25 | duplicate-ID keep-first + table warning; legacy binary-CT magic detection | `table.py` | 260 (whole Octopath table) + diagnostics | 1 | all |
| WP-26 | Lua directives (`{$STRICT}`/`{$ccode}`/`{$luacode}` no-op, accurate unknown-directive error) + phase markers as structural boundaries inside explicit `{$lua}` + redundant `{$asm}` no-op | `lua_program.py`, `aa_program.py` | 106+54+7 + ~522 cascade | 1 | all |
| WP-27 | profile-aware linked dropdowns (bit field + byte array) | `compiler.py` (guard removal), `value_types.py` (per-choice validation), `engine.py` | up to 1,215 | 2 | 30, 32/33/34 (after WP-24 merge), 28, 29, 31/35, 36 |
| WP-28 | per-program label scoping + positional `return` label | `aa_program.py`, `compiler.py` (label registry) | ~2,530 (incl. P3Reload 2,483) | 2 | 29/31/35 (disjoint hunks), 27, 30 |
| WP-29 | `alloc` in data dialect + allocation-only init profile | `aa.py`, `aa_program.py` (gate at :778), `compiler.py` (provider handling) | ~540 | 2 | 28/31/35, 27, 30 |
| WP-30 | bounded address-expression profile (typed casts as no-ops, nested indirection ≤ depth 2, `@` forms) | `address_expression.py`, `aa.py` (static token grammar), `compiler.py:206-212` routing | ~630 (incl. ~540 cascade) | 2 | all |
| WP-31 | small grammar items: 2-arg `dealloc`, multi-token `registersymbol` pre-pass, `registerlabel`, `fullaccess` no-op, `/* */` in data dialect, line-attached error messages | `aa.py`, `aa_program.py` | ~130 | 2 | 28/29/35, 27, 30 |
| WP-32 | addressless value-record demotion to non-actionable placeholders | `compiler.py` (entry policy), `table.py` (kind) | 74 | 2 | 27/33/34 (disjoint hunks), 28/29/31/35, 30 |
| WP-33 | hex bit-pattern Float/Double display + write | `compiler.py`, `engine.py` (dual guard) | 5 | 2 | 32/27/34, rest |
| WP-34 | diagnostics housekeeping: missing vs ambiguous link target; hex-string display reason; AP-08.3/08.7 alignment | `compiler.py` | 0 (diagnostics) | 2 | 32/27/33, rest |
| WP-35 | `dq`/`resb` uninitialized reservation spans (write-before-publish) | `aa_program.py`, engine coordinator | ~405 (incl. Lust 392) | 2 | 28/29/31, 27, 30, 32/33/34 |
| WP-36 | `aobscan`/`aobscanregion` staged-scan policy; `createthread` named gate message | `aa_program.py`, `compiler.py` (scan policy) | ~20-30 + gate clarity | 2 | 28/29/31/35 (disjoint hunks), rest |
| WP-37 | Lua-owned symbol handover contract (unique external provider; no foreign dealloc; ambiguous-provider rule) | `lua_program.py`, `aa_program.py:883-895`, `compiler.py` (provider map), coordinator | ~176 + 231 ambiguous | 3 | 38 (design gate first), 39, 40, 41 (soft) |
| WP-38 | runtime dynamic address provider (addressless heading bound to async/Lua provider) | plan schema, `validate_plan`, `engine.py` base resolution, re-attach re-resolution | 327 (Octopath2) | 3 | design-first; then 37/39/40/41 |
| WP-39 | trainer-creator structured per-table inspection result (supported/blocked/top-reasons/warnings) + file-level diagnostics | `converter.py` (GUI layer), plan diagnostics already in `compiler.py` | UX (all failing/warning tables) | 3 | 37, 38, 40, 41 |
| WP-40 | record hotkey registration (engine, first-wins conflict policy) + original-binding display (trainer UI) | `engine.py`, `hotkey_model.py`, `ui.py` | 37 tables / 164 entries UX | 3 | two sub-lanes (engine vs UI) independent; 39 |
| WP-41 | table-Lua execution on load — phase 1 (read-only subset; per-table bootstrap scope; writes/callbacks block with named reason) | `lua_bootstrap.py`, `lua_host.py`, engine lifecycle | 49 tables' dependent records | 3 | 39 (banner surface, soft), 37/38/40 |
| WP-42 | embedded Forms rendering (Ascii85 `TTrainerForm` decoding + control binding) | trainer UI + table model | 10 tables (low priority) | deferred | separate milestone |

Dependency notes:

- WP-27 must land **after** WP-24 (same `_dropdown` function; the
  separator policy must be in place before profile-aware choice
  validation is activated).
- WP-28 must keep the table-wide registry as the *explicit* symbol
  channel only; WP-31's `registerlabel` builds on the same registry.
- WP-37 depends conceptually on WP-28/29 ownership model stability;
  WP-38 needs the plan-schema extension reviewed before engine work.
- WP-41 soft-depends on WP-39 (banner/warning surface) but the engine
  work is independent.

## 4. Wave 1 (launch order)

Wave 1 is all low-to-medium risk, mostly parser/policy level, no
write-path semantics change. Lanes are file-disjoint:

**Lane W1-C (address grammar):** WP-22 + WP-23 (`address_expression.py`
only; unit tests in `tests/test_native_addresses.py` /
`test_native_assembler.py` expression cases).
**Lane W1-D (table robustness):** WP-25 (`table.py` only;
negative-reader tests).
**Lane W1-E (Lua dialect):** WP-26 (`lua_program.py` + `aa_program.py`;
new dedicated `tests/test_native_lua_directives.py` +
`tests/test_native_lua_phase_markers.py`).
**Lane W1-A (compiler core):** WP-19 → WP-21 → WP-24
(`compiler.py` + `engine.py` plan-validation display model; tests in
`test_native_compiler.py`, `test_native_dropdown_link.py`, new
`test_native_dropdown_separators.py`).
**Lane W1-B (globalalloc containment):** WP-20
(`global_alloc.py` + the per-entry catch hunk in `compiler.py`;
`tests/test_native_global_alloc.py` extension +
`tests/test_native_global_probe.py`).

W1-A and W1-B both touch `compiler.py` with **disjoint hunks**
(validate/offsets/dropdown vs the per-entry catch list); they run in
separate worktrees and the root merges W1-A first, then W1-B
(re-verify the full suite after each merge). Launch W1-C/D/E first,
merge, then W1-A/W1-B (or all five at once if the server load allows;
merges stay sequential).

Derivative cases for Wave 1 (land with their WPs):

| Case | WPs | Key assertions |
| --- | --- | --- |
| `case-15` "module & token shapes + offset arithmetic" | WP-19, 20, 21, 22, 23 | digit-leading module parses as module atom (bare `20` stays integer); `$process` scan plan passes `validate_plan` in all plan-ingest paths; globalalloc with `@@:` cursor compiles (no table-level exception; the cursor line never reaches `global_references`); `A::B` and `A:B` both `kind: managed`; `C00+58` → 0xC58, `A0+4*4` → 0xA0+16 folded, `1594+8+118` → 0x16B4 (5812; the earlier 0x164C literal was an arithmetic typo), `-10` signed, `20 (note)` → 0x20; negative controls (symbol offset, dotted text, empty slot) stay blocked with the exact existing reasons; 32-offset chain limit unchanged (WP-30 cast/indirection records land later as part 5) |
| `case-16` "linked dropdowns + separator rows" (part 1) | WP-24 | shared list with empty-value separator rows: linked records supported, `link_target_id` emitted, separators present as non-writable display rows, writable choice count = total − separators; comma-decimal / `??` / out-of-range choices stay blocked per choice |
| `case-20` "Lua directives & phase markers" | WP-26 | `{$STRICT}` ignored (compiles); `{$bogus}` → `Non-profile {$…} directive` named error; explicit `{$lua}` block with `[ENABLE]` inside → both phases recognized, Lua routed per phase, pre-`[ENABLE]` Lua in both phases; duplicate `[ENABLE]` stays fail-closed; redundant `{$asm}` no-op |
| `case-19` "table robustness" | WP-25 | duplicate-ID table loads (first occurrence kept, later duplicates dropped and re-reported via one table warning `Duplicate CheatEntry ID: <id> (kept first occurrence; dropped N duplicate record(s): <names>)`; children of a dropped duplicate are re-parented to the duplicate's own parent, so no unique-ID record is lost; plan total == unique source-ID count, gate:1 invariant preserved); binary-header file → named legacy-binary `TableError` (`LEGACY_BINARY_CT_HEADER`), distinct from `Invalid CT XML` (malformed XML still yields that) |

Catalog acceptance (Wave 1): reason families
`Unsupported address expression: '"$process"'.` → 0;
`Invalid address expression near '@@'` (table-level) → 0 (record-level
staged entries may appear); `Unexpected trailing address expression
tokens` (20XX) → 0; `Invalid address expression near '::…'` → 0;
`Pointer offset must be a hexadecimal integer literal` → ≤ 23 residual
(18 dotted + 2 cast/deref + 3 symbol-expression);
`Duplicate CheatEntry ID` table-level → 0 (duplicates dropped keep-first
with one table warning per ID; plan total = unique-ID count); `Invalid CT XML: syntax error: line 1, column 0` → 0
(named binary error instead); `Dropdown contains an unsupported value
expression` → ≤ 41 residual (25 comma + 12 `??` + 1 hex-styled + 3
out-of-range); `Lua/ASM delimiters must occupy standalone lines` → 0;
`Lua program phases are duplicated or out of order` → 0;
`ASM delimiter without a Lua section` → 0. Whole tables: AtomicHeart,
Cyberpunk2077, Octopath1, 20XX all compile.

## 5. Wave 2 (after Wave 1 merges; launch in batches of ≤ 3 lanes)

**Lane W2-A (compiler/value policy):** WP-27 → WP-32 → WP-33 → WP-34
(`compiler.py` + `value_types.py` + `engine.py` guards + `table.py`
kind; tests: extend `test_native_dropdown_link.py`, new
`test_native_addressless_demotion.py`, `test_native_hex_float.py`,
diagnostics tests). Cases: `case-16` (part 2: linked bit field + byte
array incl. wrong-length choice, dangling link-target diagnostic),
`case-17` (addressless templates + edge types).
**Lane W2-B (AA program dialect):** WP-28 → WP-31 → WP-35
(`aa_program.py` + `compiler.py` label registry + `aa.py`; tests: new
`test_native_label_scoping.py`, extend `test_native_assembler.py`,
`test_native_aa_literals.py`). Case: `case-18` (AA label & directive
pack).
**Lane W2-C (expression profile + scan policy):** WP-30 + WP-36
(`address_expression.py` + `aa.py` static grammar + `compiler.py`
routing/scan policy; tests: expression unit cases,
`test_native_process_aob.py` extension). Case: `case-15` (part 5:
cast/indirection address records) if not covered by W2-B's case.

Catalog acceptance (Wave 2, cumulative over Wave 1):
`Linked dropdowns for byte arrays and bit fields are unsupported` → 0
(dangling-target subset moves to the A3 residual, named per record);
`Required symbol has no unique supported provider: return.` → 0
(P3Reload table fully supported/staged); `Enable section has no
executable patch or data` → residual only for genuinely empty scripts;
`Unsupported address expression` / `Invalid address expression near`
→ residual only for documented shapes; `Unsupported AA directive:
alloc/registerlabel/fullaccess` → 0; `Symbol must contain ASCII
letters…` (2-arg dealloc / multi-token forms) → 0 (dotted-name quirk
stays, named message); `Unsupported assembler directive: dq` → 0
(reservation spans enforced write-before-publish); `Record has no
implemented native action or address` → 0 (demoted); `Value record has
no address expression` → 0 (demoted); `Hexadecimal floating-point bit
patterns are unsupported` → 0; `Dropdown link target is missing or
ambiguous` → 36 unchanged but messages split missing/ambiguous.

## 6. Wave 3 (risk-ordered; each needs its own review pass)

**WP-37 (Lua-owned symbol handover):** design the contract first
(root-owned doc in this file's §10): a program may `registersymbol` /
reference an external-owned symbol only when exactly one table record
provides it (Lua provider extraction from `lua_program.py` becomes the
`external_owned_providers` set) **and** the program never deallocates it;
wildcard `*` cleanup stays restricted to owned symbols. Fix the
ambiguous-provider rule (231 entries): deterministic unique-provider
selection or explicit ambiguity block — decide and document in the WP
design note. Runtime proof on the Windows fixture target: Lua teardown
**after** AA disable; no double-free on detach. Case: `case-24`.
**WP-38 (dynamic address provider):** plan-schema extension
(`validate_plan` schema set grows; new field naming the provider record
for an addressless heading), engine base resolution at activation,
re-attach re-resolution (saved ON-switches must re-resolve the base each
activation), UI marker on "address provided at runtime" headings.
Design gate: root reviews the schema + invalidation semantics before
implementation. Case: `case-21`.
**WP-39 (creator-UI inspection result):** structured per-table result
object from the plan (`{supported, blocked, top_reasons[], warnings[]}`);
render warnings (table Lua not executed, forms present, hotkeys
metadata-only, omitted sections) and per-record blocked reasons in the
inspection window; keep the messagebox only for unexpected errors.
Model-level tests per failure class + warning-only table; GUI smoke
test optional (Windows-only). Case: reuse `case-19` shapes.
**WP-40 (hotkeys):** engine registration through `hotkey_model`
(first-wins conflict policy + named warning; value-operation hotkeys map
only to actionable value profiles), trainer-UI display of original
bindings per record card / Info. Case: `case-23`.
**WP-41 (table-Lua bootstrap, phase 1):** per-table bootstrap scope
executed once at load; read-only subset only (existing host API
surface); top-level writes / callbacks / unsupported APIs block the
table load *activation* (not the table parse) with named reasons;
trainer-UI banner ("Table Lua not executed on load — N record scripts
stay inactive"). Case: `case-22`.

## 7. Trainer / trainer-creator UI work (cross-WP)

| Surface | Change | WP |
| --- | --- | --- |
| Trainer-creator inspection window | structured per-table result; expandable per-record blocked reasons; visible plan warnings; file-level diagnostics for the four hard failure classes (G4a-G4d shapes) | WP-39 |
| Trainer-creator | block reasons grouped by missing Lua API (profile boundary reads as one decision) | WP-39 (grouping), API list stable |
| Trainer UI | record hotkey display (original binding + active state); conflict warning banner | WP-40 |
| Trainer UI | table-Lua banner when the table carries table Lua | WP-41 |
| Trainer UI | "address provided at runtime" marker on dynamic-provider headings | WP-38 |
| Trainer UI | visual distinction heading vs blocked rows (polish, optional) | WP-32 (piggyback) |
| Both | version display / repo link already present (WP-17); no change | — |

## 8. Compatibility-assessment update protocol (root-owned, per integration)

1. **Pinned corpus:** after adding derivative case(s), re-run the full
   deterministic chain with one fresh run id
   (`reference-closure-<UTC>Z`):
   `tools/corpus_denominator/__main__.py` → `feature_matrix.py` →
   `ap11_campaign.py`; copy artifacts into `gap_inventory/`, update the
   pins in `tests/test_native_feature_matrix.py` (and the AP-11 pins).
   Gate:3 (`test_native_repro_chain.py`) re-verifies byte-identity.
2. **Feature matrix:** add one matrix row per new capability
   (partial at plan time → covered at integration, with evidence:
   modules, test files, run id). Candidate rows for this cycle:
   `validate-plan-process-token`, `globalalloc-cursor-containment`,
   `offset-arithmetic`, `digit-leading-module`, `managed-label-alias`,
   `duplicate-id-tolerance`, `legacy-binary-ct-detection`,
   `dropdown-separator-metadata`, `profile-linked-dropdowns`,
   `lua-directive-pass-through`, `phase-markers-in-explicit-lua`,
   `per-program-label-scoping`, `allocation-only-profile`,
   `bounded-expression-profile`, `aa-small-grammar`,
   `addressless-value-demotion`, `hex-float-bitpattern`,
   `link-target-diagnostics`, `dq-resb-reservation`,
   `aobscan-staged-scan`, `lua-owned-symbol-handover`,
   `dynamic-address-provider`, `creator-inspection-result`,
   `record-hotkey-registration`, `table-lua-bootstrap`.
3. **Reference-corpus catalog:** re-run the blocked catalog over the
   local scratch corpus after every merge; record per-family deltas in
   this plan's §8 changelog and in `documentation/native-progress.md`.
   This is the live "compatibility assessment" for the reference
   tables (the pinned `gap_inventory/` artifacts track the synthetic
   corpus only and stay byte-stable per run id).
4. **Ledger sync:** `documentation/native-progress.md` §4 open work +
   §2 confirmed state updated in the same commit as the plan status.

## 9. Load / parallelization policy

- Before each fan-out: `& .tools\native-build-env\Scripts\python.exe
  tools\agent_load.py` (exit 0 = at least one lane may launch, 1 =
  defer). Max 4 concurrent agents **including the root integrator**
  (continuation plan §4): with a healthy server, up to 3 subagent lanes
  per batch.
- Lane contract: `documentation/subagent-lane-rules.md` (worktree per
  WP-batch, one commit, report format §9; `TableReferences/`,
  `gap_inventory/`, `plans/`, `documentation/`, `tools/corpus_denominator/`
  are root-owned).
- Shared-file rule: no two lanes write the same file in the same batch;
  when two lanes need disjoint hunks of `compiler.py`, they run in
  separate worktrees and the root merges them **sequentially**,
  re-running the full suite after each merge.
- The root handles: all corpus additions, matrix flips, artifact
  regeneration, catalog re-runs, doc updates, merges/pushes.

## 10. Design notes owned by root (fill before WP start)

- **WP-37 ownership contract:** exact shape of
  `external_owned_providers` (per-table set built from
  `extract_lua_symbol_providers` + allocation-only program provides);
  the uniqueness rule; the ambiguous-provider resolution decision;
  the teardown-order invariant (Lua after AA); the wildcard-expansion
  boundary.
- **WP-38 plan schema:** field names, schema version handling in
  `validate_plan` (both compiler and engine gates), invalidation of
  cached plan addresses on provider re-run, re-attach re-resolution
  semantics, UI marker contract.
- **WP-41 bootstrap scope:** which host APIs count as read-only for
  the phase-1 subset; the exact named block reasons per refused API
  class; where the banner metadata lives in the plan.
- **WP-25 plan-entry model for duplicate IDs (decided 2026-10-13):**
  the FIRST occurrence is the plan entry; later duplicates are dropped
  from the plan (not emitted as addressable entries) and reported as one
  table warning `Duplicate CheatEntry ID: <id> (kept first occurrence;
  dropped N duplicate record(s): <names>)`. Rationale: the plan, the
  `by_id` map and selection persistence are ID-keyed, so exactly one
  addressable record per ID is mandatory; `gate:1`
  (`tests/test_native_table_completeness.py`) keeps its assertion
  (plan total == source-ID-set size), which the drop model satisfies
  (plan total = unique-ID count). CE keeps both entries visible in its
  UI (behavior reference only); the native equivalent of that visibility
  is the table warning + the WP-39 inspection result, not a second plan
  entry. When `case-19` is added to the pinned corpus, the gate:1 count
  assertion is updated by the root (unique-ID count for case-19).

## 11. Change log

| Date | Change | Evidence / open work |
| --- | --- | --- |
| 13.10.2026 | W1-E (WP-26) integrated (root-implemented after 3 failed lane sessions) + case-20 pinned (16th table, gate:1 → 16, chain `w1e-case20-20261013234642Z`: 6025 expected actions, weights 7369): no-op `{$...}` directive set on both AA and Lua paths, precise unknown-directive error, structural in-block `[ENABLE]`/`[DISABLE]` phase boundaries in explicit `{$lua}` chunks with shared preamble, redundant `{$asm}` no-op, contentless-`[DISABLE]` one-shot contract; reference catalog on W1-E base: D1 106 → 0, D2 54 → 0, D3 7 → 0, blocked 21,959 → 21,800 | suite 2805/25; `tests/test_native_lua_directives.py` (17 tests); W1-E merge `120da8f`; open: W1-A integration docs + case-16 (part 1) + case-15 pins, FLAG-2 dropdown residual decision, Wave 2 |
| 13.10.2026 | W1-D (WP-25) + W1-C (WP-22/23) integrated: duplicate-ID keep-first + legacy binary-CT detection, digit-leading module basenames + `Class::Method` managed-label alias; case-19 pinned (15th table, gate:1 → 15, denominator record walk deduped by ID); chain re-run `w1d-case19-20261013192913Z` (6019 expected actions, top gap cross_record_symbol 3377, weights 7365); reference catalog 21,852 → 21,851 blocked, whole-table errors 4 → 3 | suite 2758/25; `TableReferences/case-19.ct` (SHA-256 `80690e82…`); `gap_inventory/` artifacts; open: W1-A (WP-19/21/24 + plan-warning forwarding + first-wins node map), W1-B (WP-20), W1-E (WP-26 relaunched) |
| 13.10.2026 | Cycle opened: consolidated 4-lane reference-corpus assessment (`documentation/reference-gap-assessment.md`); this plan created (WP-19…WP-42, waves, cases, protocol); CE 7.5 behavior-reference boundary recorded (AGENTS.md, lane rules) | Catalog baseline 21,852 blocked / 117,019 entries / 151 tables (run `ref-assessment`); working branch `native-0.12` to be cut; Wave 1 lanes to launch after load check |
