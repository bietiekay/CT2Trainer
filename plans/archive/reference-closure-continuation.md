# CT2Trainer: Reference-Corpus Closure Plan (WP-19 … WP-58)

**ARCHIVED** — Historical plan retained for reference.


**Historical execution plan.** The reference-corpus closure cycle recorded
here is complete through Wave 4 and WP-58. WP-42 (Forms) was deferred and
may be reconsidered under the roadmap. Current state
(2026-10-20):
CT2Trainer 0.16; 30 pinned synthetic tables; 6,143 expected AP-11 actions;
feature matrix 42/42 (7,475/7,475 action-weighted); reference-corpus
assessment remains blocked at 2,698/117,624 entries; AP-11 is 0 confirmed;
Windows and Steam Deck acceptance remain open. See
[`TRACKING.md`](../TRACKING.md) and
[`documentation/native-progress.md`](../../documentation/native-progress.md)
for binding status. Do not launch the historical wave instructions below
as current work. Future reference-table coverage work will be planned in
the active
[`reference-table-100-roadmap.md`](../reference-table-100-roadmap.md).

The plan began on 2026-10-13 from `main` @ `9a76eb8` (0.11), suite 2710 OK
/ 25 skips, working branch `native-0.12`; its original scope was WP-19…WP-42
and later extended through Wave 4/WP-58.

Historical companion document: the consolidated gap assessment in
[`documentation/reference-gap-assessment.md`](../../documentation/reference-gap-assessment.md)
(root causes, counts, CE 7.5 behavior-reference notes). This historical plan preserves the work packages, ownership, sequencing,
test/fixture design, and compatibility-assessment update protocol.

## 1. Goal and completion criteria

The original cycle goal was to reduce blocked entries in a 151-table
local-only reference corpus by implementing engine features and trainer
UX. The following completion criteria describe that historical process:

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
re-run showed the expected deltas; feature matrix rows for the new
capabilities flipped to covered with evidence; build re-cut from `main`.
**Wave 3 complete (2026-10-18, on `native-0.15`):** all five Wave 3
work packages integrated (WP-37/38/39/40/41, batches 1–4, see change log)
with case-23/21/22/24 pinned as the 21st–24th corpus tables. WP-42
(Forms rendering) remained deferred at that checkpoint; this is historical
and does not define current roadmap scope.
**Wave 4 batches 1–3 complete (2026-10-19, merged into `main` @
`0c9879e`):** all six lanes integrated (w4-a: WP-43/44; w4-b: WP-46 part
1; w4-c: WP-47/55; w4-d: WP-45/56; w4-e: WP-51/48; w4-f: WP-52), with
cases 26/27/31 pinned as the 25th–27th corpus tables (chain
`w4-case31-20261019061339`: 27 tables, 6119 expected actions, weights
7446/7446, gate:1 → 27). Batch 4 was subsequently completed with WP-46
part 2, WP-49/50/53/54/57/58 and cases 28/29/30; see the 2026-10-20 log
and current status above.

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

The status cells below capture their initial planning snapshot. The dated
integration log records completion and supersedes those snapshots; WP-42
was deferred.

## 3. Master work-package table (historical scope; completed packages are not launch work)

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
| WP-34 | diagnostics housekeeping: missing vs ambiguous link target; hex-string display reason; AP-08.3/08.7 alignment; FLAG-2 dropdown follow-ups (comma-decimal Float/Double choice normalization — unblocks 25; per-choice width-precision reason for linked rows whose choices exceed value-type width — renames 31) | `compiler.py` | 0 (diagnostics) + 56 (FLAG-2) | 2 | 32/27/33, rest |
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

## 4. Wave 1 (historical launch order)

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
expression` → measured 68 residual post W1-A (exceeds the ≤ 41
expectation; FLAG-2 decision 2026-10-14: accept the named residual —
25 comma-decimal Float choice literals, 12 `??` placeholder rows in
read-only lists, 31 linked persona-list rows whose choice literals
exceed the linked record's value-type width; comma-decimal
normalization + per-choice width-precision reason are scheduled in
W2-A/WP-34, `??` placeholders stay blocked-keep); `Lua/ASM delimiters
must occupy standalone lines` → 0;
`Lua program phases are duplicated or out of order` → 0;
`ASM delimiter without a Lua section` → 0. Whole tables: AtomicHeart,
Cyberpunk2077, Octopath1, 20XX all compile.

## 5. Wave 2 (historical sequence)

**Lane W2-A (compiler/value policy):** WP-27 → WP-32 → WP-33 → WP-34
(`compiler.py` + `value_types.py` + `engine.py` guards + `table.py`
kind; tests: extend `test_native_dropdown_link.py`, new
`test_native_addressless_demotion.py`, `test_native_hex_float.py`,
diagnostics tests). Cases: `case-16` (part 2: linked bit field + byte
array incl. wrong-length choice, dangling link-target diagnostic),
`case-17` (addressless templates + edge types).
**Lane W2-B (AA program dialect):** WP-28 → WP-29 → WP-31 → WP-35
(`aa_program.py` + `compiler.py` label registry + `aa.py`; tests: new
`test_native_label_scoping.py`, extend `test_native_assembler.py`,
`test_native_aa_literals.py`). Case: `case-18` (AA label & directive
pack).
**Lane W2-C (expression profile + scan policy):** WP-30 + WP-36
(`address_expression.py` + `aa.py` static grammar + `compiler.py`
routing/scan policy; tests: expression unit cases,
`test_native_process_aob.py` extension). Case: `case-15` (part 2:
cast/indirection address records).

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

## 6. Wave 3 (historical sequence; completed)

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

## 7. Trainer / trainer-creator UI work (historical cross-WP scope)

| Surface | Change | WP |
| --- | --- | --- |
| Trainer-creator inspection window | structured per-table result; expandable per-record blocked reasons; visible plan warnings; file-level diagnostics for the four hard failure classes (G4a-G4d shapes) | WP-39 |
| Trainer-creator | block reasons grouped by missing Lua API (profile boundary reads as one decision) | WP-39 (grouping), API list stable |
| Trainer UI | record hotkey display (original binding + active state); conflict warning banner | WP-40 |
| Trainer UI | table-Lua banner when the table carries table Lua | WP-41 |
| Trainer UI | "address provided at runtime" marker on dynamic-provider headings | WP-38 |
| Trainer UI | visual distinction heading vs blocked rows (polish, optional) | WP-32 (piggyback) |
| Both | version display / repo link already present (WP-17); no change | — |

## 8. Compatibility-assessment update protocol (historical cycle procedure)

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

## 9. Load / parallelization policy (historical cycle guidance)

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

## 10. Design notes owned by root (historical designs; packages completed)

- **WP-37 Lua-owned symbol handover (designed 2026-10-14; case-24):**
  1. *`external_owned_providers` shape.* Per-table dict
     `{symbol.casefold(): provider_entry_id}` built at compile time from
     (a) `extract_lua_symbol_providers` over every record's Lua parts
     and the table-Lua source, plus (b) the `provides` sets of
     allocation-only programs (WP-29 profile). A symbol is adopted only
     when exactly one record provides it; two or more providers make the
     symbol *contested* and it stays out of the map (its references then
     keep the ordinary provider rules below). The compiler emits the map
     as `plan["external_owned_providers"]` (sorted casefolded keys, int
     provider IDs); `validate_plan` (both gates) accept it as optional
     on schema 2 and reject non-dict shapes, non-str keys, unknown
     provider IDs, and provider entries that are not supported scripts.
  2. *Reference rule.* A program may `requires` an externally owned
     symbol only if it is in `external_owned_providers` AND the program
     never unregisters or deallocates it (the symbol is not in the
     program's own `unregister`/`dealloc` op list). No AA script has to
     `registersymbol` it: the runtime registers it when the owning
     record's Lua runs. The owning record becomes the activation
     dependency of every consumer (consumers gain `dependency_ids` to
     the provider record, so ordering and the existing provider-liveness
     blocking apply exactly as for AA providers).
  3. *Ambiguous-provider resolution (the 231 reference rows).* Decision:
     **deterministic keep-first among supported providers** (document
     order, tiebreak entry ID) — the same policy as the WP-25 duplicate-ID
     keep-first. With two or more supported, non-shared-global candidates,
     the first becomes THE provider; each remaining supported duplicate is
     blocked with the named reason `Symbol provider duplicate: <sym> (kept
     provider <id>); a later registration would shadow the kept one at
     runtime.`; dependents resolve against the kept provider. Zero
     supported candidates keep the existing cascade reason `Required
     symbol has no unique supported provider: <sym>.` Rationale:
     deterministic and auditable, consistent with WP-25; CE keeps both
     entries visible (behavior reference only) — the native equivalent is
     the named duplicate block plus the WP-39 inspection result.
  4. *Teardown-order invariant.* On deactivation/detach, record AA
     programs are disabled *before* the owning record's Lua DISABLE
     phase, and any table-level teardown runs after all record teardowns,
     so an externally owned symbol is released exactly once by its owner.
     Runtime proof on the Windows fixture target: with a Lua-owned provider
     record and an AA consumer record active, detach; assert no double
     unregister, no dealloc of foreign memory, and clean journal receipts.
  5. *Wildcard boundary.* `unregistersymbol('*')` / `dealloc('*')` expand
     only to the program's own phase-owned names (symbols it registered
     and allocations it created in its ENABLE phase); they never touch
     externally owned symbols. Static guard: a program that both requires
     an externally owned symbol and contains a wildcard cleanup op is
     blocked with `Program cannot combine wildcard cleanup with externally
     owned symbol <sym>.`
- **WP-38 dynamic address provider (designed 2026-10-14; case-21):**
  1. *Schema field (additive, schema 2).* An addressless heading entry
     carries `"address_provider": {"provider_id": <int>, "symbol":
     "<name>"}` naming the provider record — a supported `script` entry
     whose `provides` contains the casefolded symbol (e.g. a table/record
     Lua that registers the computed base) — and the symbol that carries
     the base. The heading keeps `address == ""`; relative children keep
     their `+NNN` source expressions and resolve against the runtime
     base. `validate_plan` (compiler gate *and* `engine.validate_plan`)
     accept the field only when the entry has `kind == "heading"`,
     `supported is True`, `address == ""`; `provider_id` is a declared
     entry ID with `kind == "script"`, `supported is True` and the
     casefolded symbol in its `provides`; the provider is not a
     descendant of the heading it serves (no provider-to-base cycle);
     `symbol` passes `validate_symbol`. The engine keeps the heading's
     `address` empty; no resolved base is ever persisted in the plan.
  2. *Activation.* At activation of a subtree rooted at such a heading,
     the provider record must first activate successfully (its
     `registerSymbol` has run; the symbol is present in the runtime
     symbol table). Base = that symbol value, read fresh. Every relative
     child resolves from that base on this activation. If the provider is
     inactive (blocked, disabled, or failed), the heading and its whole
     subtree are activation-blocked with `Address provider <id> is not
     active.`
  3. *Re-attach re-resolution.* Saved ON-switches persist record
     selection only (existing state contract). On every activation —
     fresh attach, re-attach, or re-enable — the engine re-runs the
     provider record and re-reads the symbol; nothing caches or persists
     a resolved base across activations, and a provider whose value
     changed between activations re-bases the whole subtree on the new
     value.
  4. *Invalidation.* Compile-time: with no supported provider record
     proven by its `provides` set, the heading and its relative
     descendants keep today's named refusals (`Relative address cannot
     skip an addressless script/value ancestor.` and friends) — provider
     wiring is adopted only for proven providers. Activation-time: a
     provider failure blocks the subtree per (2) without touching sibling
     records.
  5. *UI marker contract.* A heading with `address_provider` renders the
     "address provided at runtime" marker in the trainer UI; the
     trainer-creator inspection result (WP-39) surfaces `provider_id` +
     `symbol` per such heading. The plan field is the single source of
     truth; no parallel marker metadata.
- **WP-41 table-Lua bootstrap, phase 1 (designed 2026-10-14; case-22):**
  1. *Scope and lifetime.* The combined table-Lua source (existing
     `_table_lua_source`: main `<LuaScript>` body + named tabs in document
     order) executes exactly once per table load in a dedicated read-only
     host scope built on the existing `LuaHost` with the read-only broker
     discipline (per-scope `_TransportBudget`, no target-memory mutation,
     no symbol-table writes, no assembler). The bootstrap scope persists
     for the table's lifetime so record-Lua activations see table-level
     globals; it is destroyed on table unload/detach. Phase 1 keeps no
     other persistent table-Lua state.
  2. *Read-only subset.* The allowlist is the existing
     `EngineLuaBroker.call` dispatch minus the mutation families: reads
     (`read`, `readString`, `readBytes`, `getAddress(Safe)`,
     `getModuleSize`, `getAddressOfSymbol(Safe)`, `luaEngine.snapshot`,
     `getProcHandle`, `getOpenProcessID`, `addresslist.Count`,
     `addresslist.at`, `record.get`, `isKeyPressed`,
     `getXBox360ControllerState`, `speedhack_getSpeed`, `print`,
     `AOBScan`, `scan.firstScan`, `mono_enumDomains`) stay; every call
     that mutates target memory, the symbol table, or the host session
     state, executes target code, or registers a callback is refused. The
     lane extracts the exact names from the broker dispatch; the design
     rule is that classification.
  3. *Named block reasons per refused API class (activation block, never
     parse block — the table still parses and plans):*
     - target-memory writes (`write`, `writeString`, `writeBytes`,
       `record.set`): `Table Lua uses a write API: <name>.`
     - symbol-table writes (`registerSymbol`, `unregisterSymbol`):
       `Table Lua writes the symbol table: <name>.`
     - assembler/patch execution (`autoAssemble`):
       `Table Lua executes assembler patches: <name>.`
     - target-code invocation (`executeCodeEx`, `mono_invoke_method`):
       `Table Lua invokes target code: <name>.`
     - session/UI callbacks (`showMessage`, `luaEngine.close`,
       `luaEngine.menuClick`): `Table Lua registers a UI callback:
       <name>.`
     - host-state mutation (`attachProcess`, `detachProcess`,
       `LaunchMonoDataCollector`, `speedhack_setSpeed`):
       `Table Lua mutates host session state: <name>.`
     - anything else unknown: `Table Lua calls an unsupported API:
       <name>.`
     - read-only execution that still fails: `Table Lua top-level
       execution failed: <error>.`
  4. *Banner metadata in the plan.* When the table carries Lua, the plan
     gains `plan["table_lua"] = {"executed": <bool>, "reasons": [<exact
     refusal reasons, ordered>], "record_scripts_inactive": <int>}`;
     `validate_plan` (both gates) accept the object with strict shape and
     bounded lists. `record_scripts_inactive` counts record scripts whose
     embedded Lua statically references at least one table-Lua top-level
     global (non-`local` top-level `NAME = ...` assignments in the table
     source intersected with bare identifiers in the record source,
     case-sensitive); records with no such reference stay unaffected by a
     blocked bootstrap. The existing plan warning ("Table Lua is not
     executed on load…") stays as-is; the trainer-UI banner reads the
     plan object: "Table Lua not executed on load — N record scripts
     stay inactive".
  5. *Interaction with records.* When the bootstrap is refused or fails,
     no table scope exists; dependent record scripts (per 4) stay
     inactive with the named reason, non-dependent records are
     unaffected. When the bootstrap executes cleanly (pure read-only
     table), record scripts run as today with the table globals visible
     in their scope.
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

- **WP-46 part 2 — one-shot provider handover + extended literal registerSymbol extraction (designed 2026-10-19; case-28):**
  1. *Extended extraction (`lua_symbol_providers.py`).* (a) The CE helper form
     `Register.symbol('name', …)` (case-insensitive, dotted form) counts as
     registration evidence alongside `registerSymbol('name', …)` — observed in
     the Octopath2 table (`Register.symbol('UE_version', Recorder.getStaticAddress(addr))`).
     (b) `unregisterSymbol('name')` accepts one optional trailing argument
     (e.g. `unregisterSymbol('name', false)`); the lookbehind guard that keeps
     `unregisterSymbol(` out of the register pattern is preserved. (c) All else
     unchanged: literal names only, name grammar
     `[A-Za-z_][A-Za-z0-9_]*`, comment stripping, `MAX_PROVIDERS = 64` bound
     with whole-extraction-empty behavior (never truncate).
  2. *One-shot adoption.* For records classified one-shot (missing/empty
     `[DISABLE]` — the existing one-shot classification), ENABLE-phase literal
     registration evidence is adopted into `provides` WITHOUT a matching
     unregister. Non-one-shot records keep the strict register ∩ unregister
     rule: register-only evidence stays unproven (fail-closed, unchanged).
  3. *Plan surface.* Adopted symbols merge into `entry["provides"]` as today
     (casefold-sorted). One-shot handover owners enter the existing
     `external_owned_providers` adoption rule unchanged (exactly one supported
     provider; contested symbols stay out of the map; table-Lua-claimed symbols
     stay excluded). No new plan field: the owner's one-shot nature rides on
     the owner entry's existing `one_shot` flag, which both gates re-derive
     from source.
  4. *Validator re-derivation.* The registered == unregistered == provides
     check (compiler `validate_plan`, "Script symbol dependency/registration
     metadata does not match its operations") branches on the owner entry's
     one-shot classification: non-one-shot → registered ∩ unregistered ==
     provides; one-shot → registered == provides (unregister side empty).
     Forged provides are refused by both gates as today.
  5. *Runtime handover (release-on-detach).* The owner's Lua registers the
     symbol at activation through the existing runtime path (collision
     refusal "Symbol is already owned or the activation limit is reached"
     preserved). Release happens exactly once at owner-scope retirement
     (scope close on deactivation / target exit / trainer close) — not at a
     record deactivation, since one-shot records have no disable phase —
     extending the WP-37 exactly-once-release invariant to one-shot owners.
     Consumers keep their `dependency_ids` to the owner and the existing
     provider-liveness blocking.
  6. *Scope limits / expected unblock.* Contested symbols keep the existing
     named duplicate block; table-Lua-claimed symbols stay excluded from
     handover; non-one-shot register-only stays unproven. Targets: the
     P3Reload one-shot provider shape (~124 consumer cascade), AtomicHeart
     `BaseAddress` ×15, DS2 `g_GameModule` ×10 (3-arg `registerSymbol`).
     Measured by the blocked-catalog re-run after merge.
- **WP-49 — self-provision exclusion in symbol dependency resolution (designed 2026-10-19; case-30):**
  1. *Failure shape (GC-E7; verified in `compiler.py:_dependencies` and
     AtomicHeart 239469/239470 in the reference corpus).* Record X registers
     symbol S (`registersymbol`) and defines S as its own positional label in
     its own program (separate from its alloc name, as in
     `Character_Pointer: dq 0`). When another supported record Y also
     provides S, the WP-28 label re-declaration pass re-declares X's
     positional label as an external requirement (S joins X's `requires`);
     keep-first (WP-37/45) then blocks Y as the duplicate. In the fixed-point
     pass X's only supported candidate for S is X itself → self
     `dependency_id` → the DFS marks the cycle → X is blocked with the exact
     "Symbol dependency cycle is unsupported." (the 3 named records:
     AtomicHeart / Scorn / HellPie — one such pointer-script provider per
     table). Every record depending on X cascades with "Required symbol
     provider is blocked." — the 799-record cluster (AtomicHeart 267 /
     Scorn 266 / HellPie 266, incl. `Esau_base` ×600 via id=239474). CE
     resolves symbol dependencies lazily at patch time, so a record's own
     registration satisfies its own reference; the one-pass plan must model
     this statically.
  2. *Self-provision rule.* When resolving an entry's requires, the entry
     itself is excluded from the candidate providers for symbols it provides;
     its own reference to such a symbol is satisfied by its own registration
     — no dependency edge is emitted and the record stays supported
     regardless of other providers. Other entries resolve the symbol through
     the unchanged keep-first unique-supported-provider rule (with the same
     self-exclusion: an entry never depends on itself).
  3. *True cross-record cycles stay fail-closed.* Cycles between distinct
     records (mutual or longer) remain blocked with the exact existing reason
     "Symbol dependency cycle is unsupported." (64-level depth bound
     unchanged). Rationale: a one-pass plan cannot prove an activation order
     for mutually dependent providers; CE's lazy resolution is a documented
     deviation.
  4. *Engine mirror.* The availability DFS (engine `validate_plan`,
     "Selected entry requires an unavailable symbol") and the selected
     keep-first provider pass apply the same self-provision exclusion, so a
     self-providing selected entry is not refused.
  5. *Validation.* The `dependency_ids` shape/consistency checks and the
     staged-metadata re-derivation accept the self-edge exclusion; a forged
     self-edge in `dependency_ids` is still refused.
  6. *Tests.* case-30 shape (records 70-74): the kept self-providing record
     (own positional label + `registersymbol`, plus a keep-loser duplicate
     provider) stays supported with no self-edge; its consumer gains
     `dependency_ids` to it; the duplicate stays blocked with the exact
     duplicate reason; the true mutual pair (C requires D's symbol, D
     requires C's) stays blocked with the exact cycle reason; both plan
     gates refuse forged dependency metadata (a self-edge in
     `dependency_ids` is still refused).
  7. *Expected unblock.* The GC-E7 cluster to the extent it stems from
     self-provision; the residual is measured by the post-merge catalog
     re-run (do not assume the full 799 clears).
- **WP-50 — dynamic script-parent address providers (designed 2026-10-19; case-30):**
  1. *Target shape (Octopath2-style, verified in the reference corpus).* An
     addressless record T (group heading with empty `<Address/>`, e.g.
     `moHideChildren` group "Pointer->Selected Player Data" id=23492, or an
     addressless script) carries relative children (`+220`, …). A sibling
     supported script record S (id=10050 "Playable Character Data Editor")
     computes the base at runtime (loop over a live list, possibly a
     `createTimer`) and writes it into T's address from its record Lua:
     `AddressList['<label>'].address = <expr>` — possibly via a locally bound
     constant-index array (`local mr = {AddressList['<label>'],
     AddressList['<label2>']}; … mr[2].address = addr;`) — with `…address =
     nil` in `[DISABLE]`. No symbol is registered: the base is a
     record-address write, not a symbol.
  2. *Bounded static extraction.* A new pure-text analysis beside
     `lua_symbol_provides` (lua_program.py), limited to the two idioms above:
     (a) direct `AddressList['<label>'].address = <expr>`; (b) `local <name>
     = { AddressList['<label>'], … }` (constant elements only) followed by
     `<name>[K].address = <expr>` with a constant 1-based integer K.
     `<label>` resolves to exactly one entry ID via exact description lookup
     (case-sensitive, XML-unescaped); ambiguous or missing label → no marker
     (the record keeps today's behavior). A `= nil` DISABLE counterpart for
     the same target is expected but its absence does not invalidate the
     marker (clearing also happens at scope retirement).
  3. *Plan model (additive, schema 2, no bump).* The existing
     `address_provider` marker is generalized to the target entry T:
     `{"provider_id": <int>, "symbol": <str|null>}`. `symbol == null` ⇔ WP-50
     direct address-write provider; a string symbol keeps today's WP-38
     semantics byte-identically. T must be a supported addressless heading or
     script entry (`address == ""`, `pointer_offsets == []`, not an
     addressless placeholder); S must be a supported script entry whose
     extraction names T; neither T nor S may be a descendant of the other
     (both directions).
  4. *Runtime mechanism.* New engine state `dynamic_addresses: dict[int, int]`
     (target ID → live base). The broker's record lookups
     (`addresslist.getMemoryRecordByID` / `getMemoryRecordByDescription`, and
     table-provided name lookups wrapping them) return an engine-managed
     record proxy instead of the bare entry ID: read accessors
     `ID`/`Description`/`Address` (both spellings, matching the CE field
     names) plus an `address` setter that (i) validates an int in address
     range, (ii) checks the (provider record, target ID) pair against the
     plan `address_provider` contract — only S's own live activation may
     write T; any other writer or out-of-contract target is refused with the
     named "Dynamic address write outside the planned provider contract.",
     (iii) stores `dynamic_addresses[T] = value`. `address = nil` from the
     same pair clears the entry. The engine exposes a built-in `AddressList`
     global in every record-Lua scope (name→proxy map keyed by exact record
     description); a table-defined `AddressList` shadows it in that scope
     (the Octopath2 Starter-layer equivalent). Proxies are bound to the
     requesting scope, so the setter contract check is scope-local. The
     proxy upgrade is documented in the plan note; the 27 pinned tables'
     differential compile must stay
     byte-identical (no pinned table triggers the marker, so plans are
     unchanged).
  5. *Child resolution.* Relative children of T resolve their base fresh from
     `dynamic_addresses[T]` on every access (never persisted in the plan, no
     cached base across activations — same contract as WP-38). While unset or
     S not live (`_parent_effect_live` false) the existing exact refusal
     "Address provider {provider_id} is not active." applies (provider_id =
     S). Children keep `requires: []` / `dependency_ids: []` — S is not
     auto-enabled; the user enables S and the children follow, exactly as
     WP-38.
  6. *Clearing and teardown.* S's deactivation, target exit, or trainer close
     clears `dynamic_addresses` for S's targets (analogous to symbol
     release; existing consumer-ordering guards apply); children are refused
     with the same named reason afterwards. Re-activation re-resolves live —
     timer-driven base changes between activations are followed (fresh read,
     no cache).
  7. *Validation.* Both gates: marker shape; `symbol: null` requires a
     supported script provider with the static dynamic-address extraction
     naming the target; forged markers (no extraction, wrong target, target
     not addressless, cyclic pair) are refused with named reasons.
  8. *Scope limits (documented).* Only the two static idioms are admitted;
     compatibility with real table helper layers (Octopath2's encoded
     `Starter.lua`/`Recorder.lua`, which may define their own `AddressList`
     that shadows the engine built-in) is verified under AP-11 on the real
     target; label mapping is exact-description lookup only.
  9. *Expected unblock.* GC-E8 — current exact plan-level refusal "Relative
     address has no address-bearing ancestor." (330: Octopath2 327, HFW 1,
     AtomicHeart 1, DS2 1) to the extent the shapes match the idioms;
     measured by the post-merge catalog re-run.
- **WP-53 — OS hotkey capture + group-heading hotkeys (designed 2026-10-19; case-29):**
  1. *Capture route (Windows, new module `hotkey_bridge.py`).* A hidden
     message-only Win32 window (ctypes `CreateWindowExW` + private WNDPROC
     class) is created at trainer start. Each unique registered combination
     is registered via `RegisterHotKey(hwnd, id, mods, vk)`; `WM_HOTKEY`
     maps the ID → `HotKeySpec` and enqueues it on a thread-safe queue. The
     existing 250 ms poll loop drains the queue and calls
     `engine.dispatch_hotkey(spec)` — all WP-40 model gates are unchanged
     (focus gate = target attached; first-wins dedupe; tone policy;
     `suppressed-*` statuses). `RegisterHotKey` failure
     (E_ACCESS_DENIED/E_INVALID_PARAMETER) surfaces through the existing
     `hotkey_warnings` list with a named reason ("OS hotkey registration
     failed for <key text>: <reason>."); the binding stays visible and
     programmatic dispatch keeps working. All registrations are released on
     trainer close (no OS leak).
  2. *Platform gate.* `hotkey_bridge_available()` is true on Windows only;
     elsewhere the module is a no-op and dispatch stays programmatic-only
     (non-Windows dev and Deck runs keep working; the real-OS route stays
     AP-11 evidence).
  3. *Group-heading hotkeys.* Extend `_hotkey_toggleable` to accept all
     supported group headings (today: scripts + flagged headings only). CE
     7.5 behavior reference (read-only): a group's Activate hotkey toggles
     the group's own active state; child propagation happens only with
     `moActivateChildrenAsWell`/`moDeactivateChildrenAsWell` (legacy
     `moBindActivation` loads as both). CT2Trainer terms: a flagged heading
     (existing `parent_activation`) runs the existing parent-activation
     cascade over the subtree; a plain `moHideChildren` group (e.g. Ace7
     id=8848, Alt+Insert, no cascade flags) toggles the group's own state
     only — no child propagation (CE parity). The named refusal "… not
     registered: record has no activation action." stays for blocked /
     non-toggleable rows.
  4. *Liveness and dedupe.* Group-heading bindings register when the session
     is attached (CE registers group hotkeys at table load; no
     child-liveness requirement); they join the same first-wins namespace as
     record bindings with the existing exact conflict warning.
  5. *Tests.* Dedicated `test_native_os_hotkeys.py`: fake-bridge spec
     injection → `dispatch_hotkey` with focus/dedupe/heading semantics; the
     ID→spec mapping and the failure-warning path unit-tested without a real
     window (the real `RegisterHotKey` route stays AP-11); case-29 shape:
     plain `moHideChildren` group hotkey toggles the group state without
     children; flagged group propagates through the existing cascade.
- **WP-54 — table-Lua phase 2: persistent scheduler + table-scoped symbols (designed 2026-10-19; case-29/30):**
  1. *Persistent `createTimer` (a).* Keep current behavior contractual:
     table-Lua `createTimer` at bootstrap creates a live timer in the table
     scope, ticked by the existing poll loop for the table's lifetime,
     destroyed at scope retirement. The dependent-record replay problem is
     fixed by making the table-source replay into record scopes
     *scheduler-free*: during `install_helpers` replay, `createTimer`/
     `createThread` calls in the table source bind to inert stubs (property
     assignment accepted, `destroy()` no-op, callbacks never fire), so the
     table globals establish while real timers live only in the table scope.
     Replay still refuses target-memory mutation as today (named reasons
     unchanged); record Lua's own scheduler stays real.
  2. *Table-scoped symbol registration (b).* `registerSymbol`/
     `unregisterSymbol` are admitted in the table scope, owned by the table
     scope (new owner class, distinct from record scopes). Static extraction:
     the existing literal-pair extractor applied to the combined table source
     yields a new plan field `table_lua_symbols` (casefold-sorted list;
     additive schema 2; re-derived from `plan["lua_bootstrap"]["source"]` by
     BOTH gates; forged lists refused). Residual rule (same as UDS):
     `table_lua_symbols = extracted pairs − {symbols provided by supported
     script records}` — record providers always win, so the bootstrap skips
     symbols a supported record owns (no runtime collision); under partial
     selection the table symbol registers anyway and consumers without a
     selected record provider resolve through it. Unexpected runtime
     collision → named "Table Lua symbol registration conflict: <name>."
     recorded in `table_lua.reasons` (fail-soft per WP-41).
  3. *Consumer resolution.* A record requiring a `table_lua_symbols` name
     with no supported record provider resolves through the table symbol
     like the UDS fallback (no `dependency_ids` — the table scope is live
     for the whole attach; the bootstrap precedes wish restore).
  4. *Teardown order (c).* Invert today's table-first retirement: record
     scopes retire leaves-first as today, then the table scope retires
     (table symbol release + table timer cancellation). Invariant: a table
     symbol is released exactly once, only after all record consumers are
     retired; pinned by an event-trace test (WP-37 style).
  5. *UDS reseed fix (d).* Move the `user_defined_symbols` runtime seed from
     `__init__`-only to every confirmed attach (after the target-exit symbols
     clear, before wish restore), so UDS-backed records survive re-attach
     within one trainer session; covered by a re-attach test. (Verified gap:
     engine.py seeds only at init, `self.symbols.clear()` at target exit has
     no reseed path.)
  6. *`record_scripts_inactive`* semantics unchanged (plan-level count,
     selection-independent, both gates re-derive).
  7. *Expected unblock.* GC-E17 (49 tables' dependent records, i.e. the
     `record_scripts_inactive` population) plus table-scope symbol shapes
     (GoW `goPlayer` ×28); measured by the post-merge catalog re-run.
- **WP-57 — placeholder-token AOB + region-symbol disposition (designed 2026-10-19; no new pin in B4, cycle-end case-32 decision by root):**
  1. *Token contract (from the local Plus-27 evidence,
     `sinking2-extract-crosscheck.md` §6).* Pattern-side token `s<N>.<M>` = M
     wildcard bytes at that position (observed: `s1.2` → 2 bytes, `s1.1` → 1
     byte; every observed pattern occurrence carries the byte-count suffix).
     Patch-side bare `s<N>` references the bytes captured at that token's
     position (observed uses: `db 48 8B 9F s1 00 00`, `mov rbx,[rdi+s1]`,
     `call qword ptr [rax+s1]`, `mov [rcx+s1],edx` — the byte count is taken
     from the definition, never restated). A token is defined exactly once
     per pattern; at most 16 tokens per pattern; M ∈ {1, 2}.
  2. *Scan and capture.* Patterns compile with wildcards at token positions
     (extend the shared `patterns.py` grammar; `normalize_pattern`
     canonicalizes `s<N>.<M>` as a marked wildcard span). At scan (all three
     ops: `aobscan`/`aobscanmodule`/`aobscanregion`) the matched bytes at
     each token offset are captured and stored per program activation:
     in-memory for link/stage AND in the hook journal as
     `captured_placeholders: {token: "hex"}` (persisted next to the block
     `original`; the journal survives until the exact target exits, as
     today).
  3. *Link/patch substitution.* The program-dialect assembler substitutes
     captured bytes for bare `s<N>` tokens at link time (after scan, before
     stage). The inverse-link/disable check resolves `s<N>` from the captured
     values — [DISABLE] sections use the same tokens (Plus-27 evidence) and
     disable never rescans (existing rule unchanged).
  4. *Named fail-closed refusals.* "Placeholder token s<N> is not defined in
     the scan pattern." (patch references an undefined token); "Placeholder
     token s<N> is defined more than once in the pattern."; "Placeholder
     token byte count must be 1 or 2."; "More than 16 placeholder tokens in
     one pattern."; "Placeholder tokens are not supported in assertions or
     data literals." (assert keeps its exact-bytes capture semantics; the
     data-literal path is unchanged). Scan miss keeps the existing exact
     not-found refusal.
  5. *Region symbols (`RapidFireSearchBegin` class).* No new machinery: a
     region-boundary symbol with no table provider and no UDS entry keeps
     the existing exact named refusal "Required symbol has no unique
     supported provider: <sym>." CE resolves such symbols from its global
     symbol table / other tables; CT2Trainer does not import cross-table
     symbols (documented deviation, fail-closed). Great Circle records 33-38
     (`s1.2` + external `GetCurrency`) stay blocked on the external symbol —
     correct.
  6. *Scope.* The classic dialect (`aa.py`) and the program dialect
     (`aa_program.py`) share the extended grammar via `patterns.py`; the
     nth-AOB helper and `luaCall` AOB keep their fixed-byte contract
     (placeholders there → existing refusal).
  7. *Acceptance.* Dedicated `test_native_placeholder_aob.py` (positive
     end-to-end: scan with `s1.2`, capture, patch with `db … s1 …`, exact
     disable-restore roundtrip, journal persistence across re-staging, every
     refusal above). No new pinned corpus case in B4: the GC-E20 class (26
     Plus-27 patterns + Great Circle 33-38) is measured by the post-merge
     catalog re-run; a synthetic pin (case-32) is decided by root at cycle
     end based on field evidence.

## 11. Change log

| Date | Change | Evidence / open work |
| --- | --- | --- |
| 20.10.2026 | 0.16 field-fix re-cut recorded: run `native-20261020T150115Z-c426fb92` cut from `main` @ `7616edb` via `scripts/Build-Native.ps1` (offline, hash-verified inputs); in-build suite 3398 OK / 25 regular skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per gate; `CT2Trainer-0.16-source.zip` (sha256 `35717144…`) + `CT2Trainer-0.16-windows-portable.zip` (sha256 `24050f69…`), both shipping the changelog `## 0.16` with the post-release field fixes (WP-58 UI startup crash + pagination `padx` fix, `tests/test_native_ui_button.py`) and the Sinking City 2 activation-chain runtime evidence (`tests/test_native_sc2_attach_chain.py`); supersedes the first 0.16 run `native-20261020T103508Z-0e3f9d90` (user-tested, shipped with the WP-58 startup crash) | build report `build/runs/native-20261020T150115Z-c426fb92/build.json`; local suite 3398/25 at the cut (`main` @ `7616edb`; field-fix commits `8fb13c9` + `0db2796`, docs `7616edb`); case-32 pin decision: no new corpus pin (root, cycle-end, shapes already pinned by case-31 + existing categories); open: user retest on Windows + Steam Deck (Proton) with the re-cut portable ZIP, AP-11 campaign remains the end goal |
| 20.10.2026 | 0.16 release build recorded: run `native-20261020T103508Z-0e3f9d90` cut from `main` @ `809666a` via `scripts/Build-Native.ps1` (offline, hash-verified inputs); in-build suite 3393 OK / 25 regular skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per gate; `CT2Trainer-0.16-source.zip` (sha256 `370a2d73…`) + `CT2Trainer-0.16-windows-portable.zip` (sha256 `6db5bf69…`), both shipping the changelog with the 0.16 + 0.15 + 0.14 entries. 0.16 ships the full Wave 4 feature set (WP-43…WP-57 + WP-58 UI, changelog `## 0.16`) on top of the released 0.15 content | build report `build/runs/native-20261020T103508Z-0e3f9d90/build.json`; local suite 3393/25 at the cut; `VERSION` → `0.16` incl. `__version__` sync (commit `a721d2e`); superseded runs `native-20261020T100315Z-faae4dbc` (pre changelog entry, in-build 3393/25) + `native-20261020T103508Z-0e3f9d90` (user-tested, superseded by the field-fix re-cut `native-20261020T150115Z-c426fb92`); open: user retest on Windows + Steam Deck (Proton) with the re-cut portable ZIP, AP-11 campaign remains the end goal |
| 20.10.2026 | Wave 4 batch 4 closed on `main` + canonical pin batch: all six B4 lanes on `main` (merge `0a38213` after part-2 docs `ad98565`); cases 28/29/30 pinned as the 28th–30th corpus tables (gate:1 → 30; chain `w4b4-case30-20261020081722Z`: 30 tables, 6145 records, 6143 expected actions, weights 7475/7475, top gap cross_record_symbol 3403, status 5559/544/42, categories one_shot 1730 / persistent_script 472 / value_freeze 3205, lua_host_profile 1925); feature matrix 42/42 in-scope covered | pin-batch commit `67153f0`; main suite 3393 OK / 25 regular skips (canonical path); `TableReferences/case-28.ct` (SHA-256 `89ff4243…`, 10 records / 10 actions), `case-29.ct` (`f45e6837…`, 5/5 + 1 group toggle), `case-30.ct` (`35a6000f…`, 9/9); `gap_inventory/` artifacts regenerated (run `w4b4-case30-20261020081722Z`); chain tests re-pinned across ap11 / feature-matrix / traceability / completeness / compiler / dropdown suites; reference catalog re-run post B4: 2,698 / 117,624 blocked (−934, supported 114,926 incl. 58,950 staged; 2026-10-20, `blocked-catalog-w4b4.json`); 0.16 cycle-end build done (`native-20261020T103508Z-0e3f9d90`) |
| 20.10.2026 | Wave 4 batch 4 complete on `native-0.16` @ `c2e99d8`: w4-i (WP-53 — OS hotkey capture bridge `hotkey_bridge.py` (Windows-only HWND_MESSAGE window, RegisterHotKey/WM_HOTKEY → queue, named refusal + programmatic-only fallback) + group-heading hotkeys (plain moHideChildren headings toggle own applied state without child propagation, flagged groups via the parent-activation cascade), merge `4e4973c` / lane `69516fc`) + w4-j (WP-54 — table-Lua phase 2: persistent table-scope `createTimer`, inert-stub scheduler-free record replay, table-scoped `registerSymbol` via `TableSymbolOwner`, plan field `table_lua_symbols` with both-gate byte-exact re-derivation, consumer resolution through table symbols without `dependency_ids`, inverted teardown (table scope retires last, symbols released exactly once), UDS reseed on every confirmed attach, merge `c2e99d8` / lane `d5adccf`) — all six B4 lanes now integrated; integration tree suite Ran 3393 / 3 known relocated-worktree path artifacts / 25 skips; 27 pinned corpus tables compile byte-identical (main `7a849b2` vs integrated); root real-table check round over 4 reference tables (ACE7 ColonelRVH, Ace7Gamefrf, APlagueTaleInnocence, APlagueTaleRequiem): all compile + both plan gates pass + zero regressions vs the w4-case31 catalog baseline, only plan delta the WP-53 heading-hotkey refusal removal; post-state case-29 7/7 supported (record 66 via `table_lua_symbols`), case-28/30 unchanged | pin batch done on `main` (`67153f0`); catalog re-run post B4 done (2,698 / 117,624 blocked, 2026-10-20); 0.16 cycle-end build done on main (`native-20261020T103508Z-0e3f9d90`) |
| 20.10.2026 | Wave 4 batch 4 part 1 integrated on `native-0.16` @ `668d0bc`: w4-g (WP-46 part 2 — one-shot Lua provider handover, `Register.symbol` helper form, release-on-detach exactly-once, fast-forward `0039e3e`) + w4-h (WP-49 — symbol self-provision exclusion in the label re-declaration and fixed-point passes, true cycles stay blocked, forged self-edge gate; WP-50 — `address_provider {provider_id, symbol:null}` dynamic script-parent markers, bounded `AddressList` extraction, engine `dynamic_addresses` registry + built-in read-only `AddressList` record-Lua global with contract-checked `address` setter, fresh per-access child base resolution, merge `30ce3b2` / lane `3a27ddb`) + w4-k (WP-57 — placeholder-token AOB `s<N>.<M>` scan-time capture, link-time bare `s<N>` substitution, journal-persisted `captured_placeholders`, byte-exact disable without rescan, 5 named refusals, merge `3130aa9` / lane `4f89562`) + w4-ui (WP-58 — trainer window replaced by the compact touch-first row grid: pure `ui_rows.py` row model, canvas renderer, whole-row tap, drag paging, group sections replacing breadcrumb drill-down, inline value editor, D6 state accents + transient reaction, engine contract untouched, merge `668d0bc` / lane `3f2378a`, design doc `documentation/trainer-ui-design.md`) | integration tree suite Ran 3329 / 3 known path-dependent failures (relocated-worktree path artifacts only) / 25 skips; root-verified 27/27 pinned corpus plans byte-identical base vs integrated; open: w4-i (WP-53) + w4-j (WP-54) running from `668d0bc`, pin batch for cases 28/29/30 and the 0.16 cycle-end build after their integration |
| 19.10.2026 | Wave 4 batches 1–3 complete + pin batch on `main`: all six lanes (WP-43/44, WP-46 part 1, WP-47/55, WP-45/56, WP-51/48, WP-52) merged into `main` @ `0c9879e`; cases 26/27/31 pinned as the 25th–27th corpus tables (gate:1 → 27, chain `w4-case31-20261019061339`: 27 tables, 6121 records, 6119 expected actions, weights 7446/7446, status 5539/540/42, top gap cross_record_symbol 3395); reference catalog re-run post W4: **3,632 of 117,624 blocked** (−3,945 vs 7,577 post W2-B + W2-C; supported 113,992 incl. 58,018 staged; 1 whole-table compile error, SuperMeatBoy legacy binary) | main suite 3233 OK / 25 regular skips; `TableReferences/case-26.ct` (SHA-256 `034b1d89…`, 6 records / 6 actions), `case-27.ct` (`2695fb57…`, 9/9), `case-31.ct` (`1ab46a83…`, 4/4); `gap_inventory/` artifacts (run `w4-case31-20261019061339`); catalog `blocked-catalog-w4final.json` / `.md`; open: batch 4 (WP-46 part 2, WP-49/50/53/54/57, cases 28/29/30) waits on the §3.3 design gates, WP-42 deferred, 0.16 release build at cycle end |
| 18.10.2026 | 0.15 release build recorded: run `native-20261018T055505Z-39f20180` cut from `main` @ `ed0b97b` via `scripts/Build-Native.ps1`; in-build suite 3057 OK / 25 regular skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per gate; `CT2Trainer-0.15-source.zip` (sha256 `5d5a85f6…`) + `CT2Trainer-0.15-windows-portable.zip` (sha256 `cfcc8e06…`), both shipping the elaborated release READMEs and the changelog with the 0.15 + 0.14 + 0.13 entries. 0.15 ships the prefix-cut byte-patch validation (the 0.14-ext2 Great Circle field finding: Stealth Mode and No Reload use `db 90 E9` over a 6-byte conditional jump; the stage-time complete-instruction check rejected both halves — the cut is now proven against the live target at link time and re-verified at stage time) plus the full Wave 3 feature set on top of the 0.14 content | build report `build/runs/native-20261018T055505Z-39f20180/build.json`; local suite 3057/25 at the cut; `VERSION` → `0.15` (commit `ed0b97b`); open: user retest of the Great Circle stealth/no-reload entries with the 0.15 portable ZIP, WP-42 deferred |
| 18.10.2026 | W3 batch 4 (WP-37) integrated into `native-0.15` + case-24 pinned as the 24th corpus table (gate:1 → 24, chain `w3e-case24-20261018051230`: 6100 expected actions, 6102 records, weights 7426/7426, cross_record_symbol 3385 → 3387, status 5514/538/42 → 5521/539/42, persistent_script 452 → 458 / value_freeze 3181 → 3183, lua_host_profile 1914 → 1917 / lua_symbol_api 215 → 220): Lua-owned symbol handover — per-table `external_owned_providers` map built from record-Lua registerSymbol/unregisterSymbol pairs plus allocation-only program provides (only exactly-one-supported-provider symbols; contested and table-Lua-claimed symbols stay out); duplicate providers resolve keep-first (document order, tiebreak entry ID) with the named duplicate reason; foreign-release refusals `Program may not unregister or deallocate the externally owned symbol` in both dialects (wave-B1 re-derivation for already-blocked records); wave-B2 wildcard-cleanup combination guard; consumers carry `dependency_ids`; engine teardown-order invariants (owner Lua DISABLE deferred while a consumer is live, exactly-once symbol release, leaves-first detach) proven by event-trace engine tests; both plan gates refuse forged maps | suite 3057/25; WP-37 merge `d1c1858` (lane commit `132162d`, w3-37); `TableReferences/case-24.ct` (SHA-256 `dcca38ba…`, `ct2synth24.exe`; 8 records: 2 providers + 3 consumers + keep-first pair + foreign-release refusal); `gap_inventory/` artifacts (run `w3e-case24-20261018051230`); open: 0.15 release build, WP-42 deferred |
| 18.10.2026 | W3 batch 3 (WP-41) integrated into `native-0.15` + case-22 pinned as the 23rd corpus table (gate:1 → 23, chain `w3d-case22-20261018040510Z`: 6092 expected actions, 6094 records, weights 7416/7416, cross_record_symbol 3385 unchanged, status 5514/538/42, persistent_script 452 / value_freeze 3181, lua_host_profile 1914): table-Lua bootstrap phase 1 — new `TableLuaBroker` in `lua_host.py` wraps the engine dispatch without mutation handlers and admits only the classification-extracted read names; every other call refused with its exact named reason and answered nil; plan `table_lua` metadata `{executed, reasons, record_scripts_inactive}` at plan time, strict-validated by both gates; engine runs the bootstrap exactly once per confirmed attach before wish restore (fail-soft scope persistence, legacy-plan derivation); dependent record scripts block with the named table-global reason; trainer UI banner | suite 3046/25; WP-41 merge `03010a1` (lane commit `83ba202`, w3-41); `TableReferences/case-22.ct` (SHA-256 `0f90e1bf…`, `ct2synth22.exe`); `gap_inventory/` artifacts; open: W3 batches 4, WP-42 deferred |
| 18.10.2026 | W3 batch 2 (WP-38) integrated into `native-0.15` + case-21 pinned as the 22nd corpus table (gate:1 → 22, chain `w3b-case21-20261018023823Z`: 6088 expected actions, 6090 records, weights 7413/7413, cross_record_symbol 3385 unchanged, status 5511/537/42, persistent_script 449 / value_freeze 3180, lua_host_profile 1911 / lua_symbol_api 215): runtime dynamic address provider — plan marker on the serving heading, fresh per-activation base resolution, named gate refusals, trainer UI "address provided at runtime" marker; the group heading stays a non-counted placeholder | suite 3001/25; WP-38 merge `607a4e6` (lane commit `637de28`, w3-38); `TableReferences/case-21.ct` (SHA-256 `1f4ee77e…`, `ct2synth21.exe`); `gap_inventory/` artifacts; open: W3 batches 3 + 4, WP-42 deferred |
| 18.10.2026 | W3 batch 1 (WP-39 + WP-40) integrated into `native-0.15` + case-23 pinned as the 21st corpus table (gate:1 → 21, chain `w3-case23-20261018012531Z`: 6083 expected actions, 6085 records, weights 7411/7411, cross_record_symbol 3385, status 5510/533/42): WP-40 record-hotkey registration (source `<Hotkey>` plan metadata byte-verified by both plan validators, engine first-wins registration with named deduplicated warnings, value-op dispatch through `set_value`, original-binding display + trainer-wide conflict banner, named refusals); WP-39 trainer-creator structured per-table inspection (GUI-side `table_inspection` supported/blocked/top-reasons/warnings, missing-Lua-API grouping by named API, four named file-level diagnostics, messagebox reserved for unclassified failures) | suite 2989/25; WP-40 lane `8bd58ef` (w3-40) + WP-39 lane `ef6e3f3` (w3-39) merged; `TableReferences/case-23.ct` (SHA-256 `e3568de1…`, `ct2synth23.exe`); `gap_inventory/` artifacts; open: W3 batches 2 + 3 + 4, WP-42 deferred |
| 17.10.2026 | 0.14 release build recorded: run `native-20261017T115850Z-1ebb48b7` cut from `main` @ `fca6b06` via `scripts/Build-Native.ps1`; in-build suite 2932 OK / 25 regular skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per gate; `CT2Trainer-0.14-source.zip` (sha256 `a5b075cf…`) + `CT2Trainer-0.14-windows-portable.zip` (sha256 `e57fe9b9…`), both shipping the elaborated release READMEs and the changelog with the 0.14 + 0.13 + 0.12 entries. 0.14 fixes the field finding from the 0.13 Great Circle debug log: a stale AOB pattern in saved entry 29143 raised a scan-result failure that fell into the restore loop's catch-all and blocked the whole trainer — per-wish restore isolation is now in place (`ScanMiss(ProcessMemoryError)` classifies definite scan-result failures; a failing record only fails itself, the other saved wishes keep restoring, `RetryableAction` keeps the session-level waiting handling, `StateError`/`PatchConflict` still block fail-closed) and the debug log now names every program (AA script) preflight scan (`scan` / `scan-failed` with entry_id/symbol/module/pattern, module base/size/RVA, full traceback on failure) | build report `build/runs/native-20261017T115850Z-1ebb48b7/build.json`; local suite 2932/25 at the cut; open: user retest of the four saved Great Circle toggles (29138/29143/29145/29149) with the 0.14 portable ZIP, runtime export for allocation-only providers (Wave 3), Wave 3 (WP-37/38/39/40/41), WP-42 deferred |
| 16.10.2026 | 0.13 release build recorded: run `native-20261016T190005Z-b3139b30` cut from `main` @ `d57e62c` via `scripts/Build-Native.ps1`; in-build suite 2927 OK / 25 regular skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per gate; `CT2Trainer-0.13-source.zip` (sha256 `23b57307…`) + `CT2Trainer-0.13-windows-portable.zip` (sha256 `d7f64efb…`), both shipping the elaborated release READMEs (the portable user guide now documents the optional debug logging) and the changelog with the 0.13 + 0.12 entries. 0.13 adds the user-requested runtime debug logging option (converter checkbox / CLI `--debug-log`, per-event JSON log next to the trainer EXE, off by default) and the module-snapshot fallback for Win32 error 299 (field finding from the first 0.13 debug log: the combined native/WOW64 toolhelp snapshot fails on some Windows builds; the native-only flag is retried before failing) on top of the unchanged 0.12 Wave 2 content | build report `build/runs/native-20261016T190005Z-b3139b30/build.json`; superseded 0.13 run `native-20261016T181516Z-b8ae88de` (pre module-snapshot fallback, in-build 2925/25); open: runtime export for allocation-only providers (Wave 3), Wave 3 (WP-37/38/39/40/41), WP-42 deferred |
| 16.10.2026 | 0.12 release build recorded: run `native-20261016T163910Z-d047f2d2` cut from `main` @ `ba1d3e4` via `scripts/Build-Native.ps1`; in-build suite 2910 OK / 25 regular skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per gate; `CT2Trainer-0.12-source.zip` (sha256 `f5a5468d…`) + `CT2Trainer-0.12-windows-portable.zip` (sha256 `7bd582e3…`), both shipping the elaborated release READMEs (product overview, capabilities, usage) and the changelog with the 0.12 + retro 0.11 entries. GOAL-7 closed | build report `build/runs/native-20261016T163910Z-d047f2d2/build.json`; superseded 0.12 runs `native-20261016T154141Z-2de774ab` (pre release-docs) and `native-20261016T161905Z-e8ef67a0` (byte-identical re-cut); open: runtime export for allocation-only providers (Wave 3), Wave 3 (WP-37/38/39/40/41), WP-42 deferred |
| 16.10.2026 | W2-B (WP-28/29/31/35) integrated + case-18 pinned as the 20th table (gate:1 → 20, chain `w2b-case18-20261016142912Z`: 6080 expected actions, 6082 records, weights 7408/7408, cross_record_symbol 3384, status 5507/533/42): WP-28 two-stage per-program label scoping (own bare positional labels local at the prepare level; re-declared as external requirements when another supported record provides the same symbol — registered symbols win over local labels); WP-29 `alloc` in the data dialect + allocation-only init profile (no game write; `dealloc`/`unregistersymbol` on disable; no dead-allocation publication); WP-31 data-dialect grammar (2-arg `dealloc`, multi-token `registersymbol` pre-pass, `registerlabel`, `fullaccess` no-op, `/* */` comments, line-attached errors, `inert/documented` comment-only classification); WP-35 operand-less `dq`/`resb` reservation spans (program-owned, written before publish, no cross-program access). case-18: 18 records (IDs 10–27), 16 supported / 2 deliberately kept blocked (IDs 26/27: globalalloc DISABLE re-initialization, label inside a global initializer — W2-C named keep-block reasons) | suite 2910/25; W2-B merge `2f68f80` (lane commit `d4d062d`); `TableReferences/case-18.ct` (SHA-256 `e3405ebc…`, `ct2synth18.exe`; pin commit `dbeee04`); `gap_inventory/` artifacts (run `w2b-case18-20261016142912Z`); open: runtime export for allocation-only providers (engine.py wiring, Wave 3), Wave 3 (WP-37/38/39/40/41), WP-42 deferred, 0.12 release build |
| 15.10.2026 | W2-C (WP-30/36) integrated + case-15 (part 2) refined and re-pinned (chain `w2c-case15p2b-20261015144326Z`: 6,062 expected actions, 6,064 records, weights 7381 → 7387, top gap cross_record_symbol 3377 → 3381, status 5487/533/39 → 5492/532/40): WP-30 bounded address-expression profile (typed casts as no-ops for symbol extraction, nested indirection ≤ depth 2, `@` forms; `requires == address symbols` match gate kept); WP-36 `aobscan`/`aobscanregion` staged under the existing scan budget, `createthread` keeps the capability gate with the named reason, 3-arg `globalalloc(sym,size,$process)` accepted | W2-C merge `32e0cdd` (lane commit `e5c039e`); `TableReferences/case-15.ct` (SHA-256 `5bc013eb…`, 21 records; pin commit `8f8fb48`); `gap_inventory/` artifacts (run `w2c-case15p2b-20261015144326Z`) |
| 14.10.2026 | W2-A (WP-27/32/33/34) integrated + case-16 part 2 and case-17 pinned (19th table, gate:1 → 19, chain `w2a-case17-20261014112532Z`: 6,057 expected actions, 6,059 records incl. 2 navigation, weights 7381/7381, top gap unchanged cross_record_symbol 3377, status 5487/533/39, categories custom_value 4 / navigation 2 / one_shot 1723 / persistent_script 431 / string_write 732 / value_freeze 3167): WP-27 profile-aware linked dropdowns (per-choice validation, family 1,215 → 0); WP-32 addressless demotion (23 + 51 → 0, placeholder headings, cascade exclusion); WP-33 hex IEEE-754 bit-pattern (5 → 0); WP-34 named diagnostics (generic link-target message → 0, comma-decimal normalization, width-precision naming, AP-08.7 citation, FLAG-2 residual 68 → 13). Reference catalog: blocked 10,892 → 9,962 (−930, no supported regressions; +197 records re-surfaced as named missing-target rows). Denominator tooling made navigation-aware (category_counts_sum, ap11 per-table `navigation_excluded` + report-side checks, guarded failure printers). Open: W2-B (WP-28/29/31/35/36, case-18), W2-C (WP-30/36 follow-up, case-15 part 2) | suite 2840/25; W2-A merge `aa6371b` (lane `a49a1db`); `TableReferences/case-16.ct` (SHA `cf7ef73a…`), `TableReferences/case-17.ct` (SHA `893f961c…`); `gap_inventory/` artifacts (run `w2a-case17-20261014112532Z`); catalog delta `Temp\opencode\refassess\blocked-catalog-w2a.json` + `delta-w2a.txt` |
| 14.10.2026 | case-15 (part 1) pinned as 18th table (gate:1 → 18, chain `w1a-case15-20261014011543Z`: 6047 expected actions, weights 7376/7376, top gap unchanged cross_record_symbol 3377, status 5482/528/37, categories persistent_script 431 / value_freeze 3159): digit-leading module atom (`20XX.exe+47B88B8` supported, bare `20XX` stays blocked), `$process` AOB scan record (WP-19), `@@:` globalalloc cursor record (WP-20), `Synth:Alpha`/`Synth::Beta` managed labels verbatim (WP-23), pointer-offset folding incl. signed/annotated forms (WP-21: `C00+58` → 0xC58, `A0+4*4` → 0xB0, `1594+8+118` → 0x16B4, `-10`, `20 (name pointer)` → 0x20) with literal refusals for symbol/dotted/empty-annotation offsets and the 32-offset chain limit; part 2 (cast/indirection record) lands with WP-30 | `TableReferences/case-15.ct` (SHA-256 `cdc1ad6c…`, `ct2synth15.exe`); `gap_inventory/` artifacts; suite 2805/25 |
| 14.10.2026 | W1-A (WP-19/21/24 + WP-25 follow-ups) integrated + case-16 (part 1) pinned (17th table, gate:1 → 17, chain `w1a-case16-20261014003107Z`: 6031 expected actions, weights 7371): WP-19 `$process` AOB scan token passes both plan validators (forged scan modules stay rejected); WP-21 pointer-offset hex constant folding (`1594+8+118` → 0x16B4, signed-64 range checks, 32-offset cap kept, literal refusals kept; family 239 → 23, within plan ≤ 23); WP-24 empty-value dropdown rows = non-writable separator metadata (own + linked borrowing, read-only concrete-choice rule, forged-separator refusals in both validators; family 10,935 → 68); WP-25 follow-ups (keep-first `_entry_node_maps`, table-reader warning forwarding). FLAG-2 decision: accept the 68 dropdown residual as a named family (25 comma-decimal Float + 12 `??` placeholder + 31 linked width-exceeding persona-list rows); comma-decimal normalization + per-choice width reason scheduled in W2-A/WP-34, `??` stays blocked-keep. Reference catalog post W1-A + W1-E: 21,959 → 10,892 blocked / 117,624 (1 whole-table error: SuperMeatBoy legacy binary); top families now GlobalWorkPtr 2509 (WP-28), Character_Pointer 1310 (WP-37 cascade), linked-dropdown 1215 (WP-27) | suite 2805/25; `TableReferences/case-16.ct` (SHA-256 `4f1571b2…`); `gap_inventory/` artifacts (run `w1a-case16-20261014003107Z`); W1-A merge `01a24c5` |
| 13.10.2026 | W1-B (WP-20) integrated: NASM `@@` current-address cursor (`@@:` handled positionally in `prepare_global_program`, named per-entry refusals elsewhere, `AddressExpressionError` added to the compiler per-entry catch list); Cyberpunk2077.CT compiles (241 supported / 108 blocked, 0 `@@` reasons) | suite 2769/25; W1-B merge `ccb698a` (+ tracker commit `916bb82`); `src/ct2trainer/native/global_alloc.py`, `tests/test_native_global_alloc.py`, `tests/test_native_global_probe.py` |
| 13.10.2026 | W1-E (WP-26) integrated (root-implemented after 3 failed lane sessions) + case-20 pinned (16th table, gate:1 → 16, chain `w1e-case20-20261013234642Z`: 6025 expected actions, weights 7369): no-op `{$...}` directive set on both AA and Lua paths, precise unknown-directive error, structural in-block `[ENABLE]`/`[DISABLE]` phase boundaries in explicit `{$lua}` chunks with shared preamble, redundant `{$asm}` no-op, contentless-`[DISABLE]` one-shot contract; reference catalog on W1-E base: D1 106 → 0, D2 54 → 0, D3 7 → 0, blocked 21,959 → 21,800 | suite 2805/25; `tests/test_native_lua_directives.py` (17 tests); W1-E merge `120da8f`; open: W1-A integration docs + case-16 (part 1) + case-15 pins, FLAG-2 dropdown residual decision, Wave 2 |
| 13.10.2026 | W1-D (WP-25) + W1-C (WP-22/23) integrated: duplicate-ID keep-first + legacy binary-CT detection, digit-leading module basenames + `Class::Method` managed-label alias; case-19 pinned (15th table, gate:1 → 15, denominator record walk deduped by ID); chain re-run `w1d-case19-20261013192913Z` (6019 expected actions, top gap cross_record_symbol 3377, weights 7365); reference catalog 21,852 → 21,851 blocked, whole-table errors 4 → 3 | suite 2758/25; `TableReferences/case-19.ct` (SHA-256 `80690e82…`); `gap_inventory/` artifacts; open: W1-A (WP-19/21/24 + plan-warning forwarding + first-wins node map), W1-B (WP-20), W1-E (WP-26 relaunched) |
| 13.10.2026 | Cycle opened: consolidated 4-lane reference-corpus assessment (`documentation/reference-gap-assessment.md`); this plan created (WP-19…WP-42, waves, cases, protocol); CE 7.5 behavior-reference boundary recorded (AGENTS.md, lane rules) | Catalog baseline 21,852 blocked / 117,019 entries / 151 tables (run `ref-assessment`); working branch `native-0.12` to be cut; Wave 1 lanes to launch after load check |
