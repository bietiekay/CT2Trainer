# CT2Trainer — Central Gap & Goal Tracking

**Status: 2026-10-13** (baseline `main` @ `9a76eb8`, 0.11, build
`native-20261012T092729Z-2d8aaf12`, suite 2710 OK / 25 expected skips).

This is the **single central tracking document** for every gap and every goal
of the project. It is maintained by the root agent on every integration and is
the first place to look for "what is open, who owns it, what is the next
action". Detailed analysis and per-package engineering notes live in the
linked documents and are NOT duplicated here:

- Gap analysis (reference corpus, root causes, CE 7.5 behavior reference):
  [`documentation/reference-gap-assessment.md`](../documentation/reference-gap-assessment.md)
- Implementation detail (WP scopes, test design, fixture specs, wave plan):
  [`reference-closure-continuation.md`](reference-closure-continuation.md)
- Legacy AP-01…AP-12 plan history:
  [`native-implementation-continuation.md`](native-implementation-continuation.md)
- Confirmed-state ledger (builds, suites, acceptance records):
  [`documentation/native-progress.md`](../documentation/native-progress.md)
- Machine-readable feature matrix: [`gap_inventory/feature-coverage.json`](../gap_inventory/feature-coverage.json)
- Machine-readable reference-corpus catalog (local-only, not committed):
  `Temp\opencode\refassess\blocked-catalog.json`

## Status legend

| Token | Meaning |
| --- | --- |
| `done` | merged + tested + matrix flipped (if applicable) |
| `active` | lane running or root work in flight |
| `ready` | fully specified, not started |
| `design` | design gate must close before implementation |
| `open` | known open, not yet scheduled |
| `blocked-keep` | deliberately kept fail-closed (malformed input / declared scope boundary); tracked as documented residual, not a defect |
| `cascaded` | not an independent root cause; unblocks when the owning upstream WP lands |

## 1. Goals (outcomes)

| ID | Goal | Status | Definition of done / current state |
| --- | --- | --- | --- |
| GOAL-1 | Feature matrix 100% in-scope coverage without AP-11 | **done** (2026-10-11) | 42/42 features covered, 7361/7361 action-weighted (run `wp14-staged-20261011T093320Z`). Gates 1–3 closed with tested evidence. |
| GOAL-2 | Reference-corpus closure: 151 local-only tables | **active** (since 2026-10-13, cycle `native-0.12`) | Baseline 21,852 / 117,019 entries blocked (4 whole-table compile errors). Target ≈ 85 % closure via WP-19…WP-42; residue must be `blocked-keep` with named reasons. Every closure measured by blocked-catalog re-run (§4). |
| GOAL-3 | AP-11 real-game confirmation (6011 pinned actions) | **open** (separate end goal) | 0 confirmed. Manifest `gap_inventory/ap11-campaign.json`; runbook `documentation/native-ap11-campaign.md`. Excluded from the feature metric by definition. |
| GOAL-4 | Final acceptance Windows (clean PC/VM, no CE/Python) | **open** | Portable start, trainer run, Unicode paths, UAC/rights, debugger conflict, saved-wish replay, target restart. Last user-tested release: 0.9.0-rc2 (`native-20261010T172336Z-ffe35eb0`). |
| GOAL-5 | Final acceptance Steam Deck (real Proton, touch) | **open** | Protocol `tests/deck/compatibility-matrix.md`. |
| GOAL-6 | `runtime_unverified` flipped | **open** | Requires GOAL-4 + GOAL-5 evidence recorded in `documentation/native-verification.md`. |
| GOAL-7 | Release 0.12 (end of closure cycle) | **open** | After Wave 1+2 integrations are stable: full suite green, matrix artifacts regenerated, both ZIPs via `scripts/Build-Native.ps1`, `ce_inputs: []`. |

## 2. Gap inventory — reference corpus (21,852 blocked entries)

Baseline measured 2026-10-13 (run `ref-assessment`): 151 tables, 117,019 plan
entries, 95,167 supported (incl. 46,987 staged), 21,852 blocked, 725 distinct
reasons. IDs are stable; do not renumber.

### 2.1 Whole-table compile failures (4 tables, 629+ entries)

| ID | Table | Gap | Entries | Owning WP | Status |
| --- | --- | --- | ---: | --- | --- |
| GC-T1 | AtomicHeart-Win64-Shipping.CT | `$process` scan module rejected by `validate_plan` (compile path already accepts it: `aa.py:205`, `aa_program.py:326-328`) | 20 | WP-19 | ready |
| GC-T2 | Cyberpunk2077.CT | NASM `@@` cursor in globalalloc escapes per-entry catch (`AddressExpressionError` not in `compiler.py:619` list) + `global_alloc.py:149` misclassifies `@@:` | 349 | WP-20 | ready |
| GC-T3 | Octopath_Traveler-Win64-Shipping.CT | 24 duplicated CheatEntry IDs → table-level `TableError` | 260 | WP-25 | ready (design note: keep-first plan-entry model, see §3 WP-25) |
| GC-T4 | SuperMeatBoy.CT | legacy binary CE 5.x table, not XML | n/a | WP-25 | ready (named-error polish; keeps fail-closed) |

### 2.2 Address-expression family (Lane B)

| ID | Gap | Entries | Root cause | Owning WP | Status |
| --- | --- | ---: | --- | --- | --- |
| GC-B1 | `$process` token in `validate_plan` | 20 | consistency bug (see GC-T1) | WP-19 | ready |
| GC-B2 | `@@` cursor handling + error containment | 349 | parser gap + exception-type escape | WP-20 | ready |
| GC-B3 | pointer offsets with constant arithmetic (`C00+58`, `13A8+118`, `A0+4*4`, `433c+10c*4`) | 201 of 239 | `_offsets` (`compiler.py:67-82`) requires bare hex; the address grammar already evaluates these — fold via `parse_expression` with pure-integer AST gate | WP-21 | ready |
| GC-B3b | annotated hex offsets (`20 (Offset of the name pointer)`) | 15 (in the 239) | same | WP-21 | ready |
| GC-B3c | dotted-ident offsets (`GameEngine.GameInstance`) | 18 (in the 239) | malformed authoring input (not usable in CE either) | — | blocked-keep (named reason) |
| GC-B3d | cast/deref offsets (`(dword)[pInventoryItemResource+B8]*4`) + symbol-expression offsets | 5 (in the 239) | needs per-step runtime pointer-chase semantics; no corpus evidence of broader use | — (future) | open (deferred) |
| GC-B4 | digit-leading module basenames (`20XX.exe+47B88B8`) | 10 (whole table) | `_TOKEN` has no digit-leading `name.(exe|dll)` alternative | WP-22 | ready |
| GC-B5 | `Class::Method` double-colon managed labels | ~15 (Kena 10, BatmanAK 5) | `_MANAGED_LABEL` allows single colon only | WP-23 | ready |
| GC-B6 | relative addresses under addressless script-parent providers (`Recorder.writeAddress` pattern, Octopath2) | 327 of 331 | no runtime dynamic address provider concept; static compilation cannot see it | WP-38 | design (schema + engine contract first) |
| GC-B7 | SOTTR addressless-header trees | 10 (+3 via GC-B3d) | degenerate input; current reasons correct | — | blocked-keep |

### 2.3 Dropdown / value-record family (Lane A)

| ID | Gap | Entries | Root cause | Owning WP | Status |
| --- | --- | ---: | --- | --- | --- |
| GC-A1 | dropdown choice rows with empty values (separator rows) poison every linked record | 10,894 (10,859 linked + 35 own-list) | `_dropdown` validates every choice as a literal; only `*` is skipped (`compiler.py:141-150`, `table.py:86-107`) | WP-24 | ready |
| GC-A2 | linked dropdowns for `Binary` bit fields / `Array of byte` records | up to 1,215 | blanket `value_profile` guard at `compiler.py:132-133`; engine write path already capable (WP-15 + `parse_profile_value`) | WP-27 | ready |
| GC-A3 | dangling `DropDownListLink` targets | 36 | missing targets (no ambiguity); CE shows empty dropdown | WP-34 | ready (keep blocked; split missing/ambiguous messages) |
| GC-A4 | addressless value records (simple types) | 23 | template/placeholder rows; demote to non-actionable display placeholder | WP-32 | ready |
| GC-A5 | addressless value records (profile types) | 51 | same | WP-32 | ready |
| GC-A6 | String records with `ShowAsHex` | 15 | string codec is literal-text-only; byte-view is a different codec | WP-34 | ready (keep blocked, clearer reason; optional read-only hex view later) |
| GC-A7 | Float/Double `ShowAsHex` bit-pattern editing | 5 (trine4) | dual guard (compiler + engine) refuses hex-float edit | WP-33 | ready |
| GC-A8 | Custom value types without static definition (RE2-style, table-Lua-defined) | 6 | runtime-Lua definition; converter contractually does not execute table Lua | — | blocked-keep (align AP-08.3/08.7 citation; part of WP-34 housekeeping) |

### 2.4 AA grammar / symbol-ownership family (Lane C)

| ID | Gap | Entries | Root cause | Owning WP | Status |
| --- | --- | ---: | --- | --- | --- |
| GC-C1 | positional `return:` labels after AOB injection (table-wide label registry drops multi-definer names; P3Reload chain 2,483) | ~2,530 | per-program label scoping missing; CE scopes labels per script (`autoassembler.pas` local label table) | WP-28 | ready |
| GC-C2 | `alloc` in data path + allocation-only init scripts | ~540 | `alloc` not in data-dialect directives; enable-section gate at `aa_program.py:778` requires executable patch | WP-29 | ready |
| GC-C3 | Lua-allocated symbols consumed by AA scripts (DS2 `KeyHandlerThread` etc.) | ~176 direct + 120 cascade | strict ownership model (`aa_program.py:883-886`); needs explicit handover contract | WP-37 | design |
| GC-C4 | cast + nested-indirection address expressions (`(DWORD)[X+3]+X+7`) | ~630 incl. ~540 cascade | bounded static expression profile lacks cast/indirection forms | WP-30 | ready |
| GC-C5 | operand-less `dq`/`resb` reservation | ~405 incl. 392 cascade | reservation without initializer not supported | WP-35 | ready |
| GC-C6 | small grammar items: 2-arg `dealloc`, multi-token `registersymbol` pre-pass, `registerlabel`, `fullaccess` no-op, `/* */` in data dialect, line-attached errors | ~130 incl. 33 cascade | individual directive gaps | WP-31 | ready |
| GC-C7 | process-wide `aobscan`/`aobscanregion`; `createthread` gate message | ~20-30 | scan-policy gate + capability gate (keep gated, name it) | WP-36 | ready |
| GC-C8 | no-action / comment-only scripts | 38 | classified as blocked; should be `inert/documented` display state | WP-31 (reporting part) | ready |
| GC-C9 | global-init profile residuals (3-arg `globalalloc(sym,size,$process)`, label-based initializers) | ~5 | profile deliberately bounded; accept process-anchored 3-arg form | WP-36 (3-arg form) / — (labels stay blocked-keep) | ready / blocked-keep |

### 2.5 Lua / host / UX family (Lane D)

| ID | Gap | Entries / scope | Root cause | Owning WP | Status |
| --- | --- | ---: | --- | --- | --- |
| GC-D1 | non-conditional `{$…}` directives rejected (`{$STRICT}` ×86 raw occurrences) | 106 | whitelist only if/else/endif/define (`aa_program.py:73-78`); misleading error text (`lua_program.py:144-148`) | WP-26 | ready |
| GC-D2 | `[ENABLE]`/`[DISABLE]` inside explicit `{$lua}` blocks | 54 | phase marker honored only when `implicit_lua` (`lua_program.py:289`); CE splits phases on raw text before Lua expansion (verified in CE 7.5) | WP-26 | ready |
| GC-D3 | redundant `{$asm}` rejected | 7 | CE blanks stray `{$ASM}` lines; native raises | WP-26 | ready |
| GC-D4a-d | whole-table failures (= GC-T1…T4) | 4 tables | see §2.1 | WP-19/20/25 | ready |
| GC-D4e | trainer-creator UI: single bare messagebox; plan warnings never displayed | all failing + warning tables | no structured inspection result in GUI | WP-39 | ready |
| GC-D5 | table `<LuaScript>` not executed on load (read-only replay only) | 49 tables | no per-table bootstrap scope | WP-41 | design (phase 1: read-only subset) |
| GC-D6 | Lua host API surface below corpus usage (Forms API, debugger API, `createMemoryRecord`, found-list mutation) | per API, fail-closed by design | declared profile boundary | WP-39 (UI grouping) / no engine change | blocked-keep (boundary) |
| GC-D7 | record hotkeys: model exists, nothing registered or displayed | 37 tables / 164 entries / 247 hotkeys | no engine registration + no UI display | WP-40 | ready |
| GC-D8 | embedded `<Forms>` ignored (7 Ascii85 `TTrainerForm` blobs + 24 child elements) | 10 tables | needs CE form binary format; high effort | WP-42 | open (deferred milestone) |
| GC-D9 | description-only records / group headers | 5,179 (5,105 headers + 74 leaves) | verified acceptable (headings, not errors) | — | blocked-keep (polish optional: heading vs blocked row visual, expand/collapse) |

### 2.6 Provider cascade (derived, not independent)

`Required symbol has no unique supported provider` = 8,372 entries +
`Symbol provider is ambiguous` = 231 entries. These unblock when the owning
upstream WPs land. Largest chains (verified 2026-10-13):

| Entries | Provider | Unblocks via |
| ---: | --- | --- |
| 2,483 | P3Reload `GlobalWorkPtr` | WP-28 (GC-C1) |
| 1,250 / 540 / 481 | AtomicHeart v1.2 `Character_Pointer` / `Esau_base` / `Character2_Pointer` | symbol-ambiguity resolution (WP-37 scope) + WP-24/26 for provider scripts |
| ~349 | GhostOfTsushima `pplayeraddress` | WP-30 (GC-C4) |
| ~300 / ~230 | Lust from Beyond `_playerbase` / DS2 `DSPlayerEntity` | WP-35 (GC-C5) / WP-26 (GC-D1/D2) |
| ~220 | Horizon `LocalPlayer` (both tables) | WP-26 (GC-D1/D2) |
| ~514 | DeathStrandingDC base script | WP-29 (GC-C2) |
| 227 | no provider record in table at all (39 tables; may be table-Lua-provided) | re-measure after WP-41 |

## 3. Work-package status (all cycles)

### 3.1 Completed (0.9 … 0.11)

| WP | Scope | Merged at | Evidence |
| --- | --- | --- | --- |
| AP-01…AP-10 | see `native-implementation-continuation.md` §5 | `b6c48cc` … `54b172e` | gates 1–3 closed, matrix 39/39 |
| WP-14 | staged capabilities (signed offsets, script-parent cascades, staged gating, record-ID activation sets, `case-14.ct`) | `54b172e` (0.10) | PRAGMATA 586/416/9 |
| WP-15 | L2-37 executable bit-field writes | `d3316aa` (0.11) | suite 2688→… |
| WP-16 | named table-Lua tabs (L5-19) | `38a830d` | suite 2679 |
| WP-17 | version display + repository link | `557b2ac` | suite 2698 |
| WP-18 | `$process` AOB module token + trailing `@F` fallback | `9a76eb8` (0.11) | PRAGMATA 595/0; suite 2710 |

### 3.2 Reference-closure cycle (this cycle, `native-0.12`)

| WP | Title | Wave | Touches | Unblocks (est.) | Corpus case(s) | Status |
| --- | --- | --- | --- | ---: | --- | --- |
| WP-19 | `$process` in `validate_plan` (one-line mirror of `aa.py:205`) | 1 | `compiler.py` | 20 + all future `$process` plans | case-15 | ready |
| WP-20 | `@@` cursor in globalalloc + per-entry containment of `AddressExpressionError`/`GlobalError` | 1 | `global_alloc.py`, `compiler.py` (catch list) | 349 (whole table) | case-15 | ready |
| WP-21 | pointer-offset constant folding + annotated-hex normalization (pure-integer AST gate; keep 32-offset cap) | 1 | `compiler.py` `_offsets` | 216 | case-15 | ready |
| WP-22 | digit-leading module basenames in `_TOKEN` (ordered before bare-integer alternative) | 1 | `address_expression.py` | 10 (whole table) | case-15 | active (lane W1-C, branch `w1-c`, worktree `side/w1-c`) |
| WP-23 | `::` managed-label alias (resolution unchanged) | 1 | `address_expression.py` | ~15 | case-15 | active (lane W1-C, branch `w1-c`, worktree `side/w1-c`) |
| WP-24 | empty-value dropdown rows = non-writable separator metadata (own + linked lists); keep all other non-literals fail-closed | 1 | `compiler.py` `_dropdown` + plan/engine validation | 10,894 | case-16 | ready |
| WP-25 | duplicate-ID keep-first + blocked duplicate + table warning; binary-CT `CHEATENGINE\t` magic → named `TableError` (malformed XML keeps its reason) | 1 | `table.py` | 260 (whole table) + diagnostics | case-19 | active (lane W1-D, branch `w1-d`, worktree `side/w1-d`; keep-first model decided, plan §10) |
| WP-26 | Lua directives (`{$STRICT}`/`{$ccode}`/`{$luacode}` no-op pass-through; accurate unknown-directive error) + phase markers structural inside explicit `{$lua}` blocks (close chunk at marker, route text per phase, pre-`[ENABLE]` runs in both phases) + redundant `{$asm}` no-op | 1 | `lua_program.py`, `aa_program.py` | 167 direct + ~522 cascade | case-20 | active (lane W1-E, branch `w1-e`, worktree `side/w1-e`) |
| WP-27 | profile-aware linked dropdowns (remove `value_profile` guard; per-choice `parse_profile_value`; mixed-length byte-array choice → per-record block naming the choice) | 2 | `compiler.py`, `value_types.py`, `engine.py` validation | up to 1,215 (−≥204 dangling) | case-16 | ready (after WP-24 merge) |
| WP-28 | per-program label scoping; positional `return:` label resolves to own patch end; table-wide registry becomes explicit symbol channel only | 2 | `aa_program.py`, `compiler.py` label registry | ~2,530 | case-18 | ready |
| WP-29 | `alloc` in data dialect + allocation-only init profile (no game write; `dealloc`/`unregistersymbol` on disable; no dead-allocation publication) | 2 | `aa.py`, `aa_program.py`, compiler provider handling | ~540 | case-18 | ready |
| WP-30 | bounded expression profile: typed casts as no-ops for symbol extraction, nested indirection ≤ depth 2, `@` forms; keep `requires == address symbols` match gate | 2 | `address_expression.py`, `aa.py`, `compiler.py:206-212` | ~630 | case-15 | ready |
| WP-31 | small grammar items: 2-arg `dealloc`, multi-token `registersymbol` data-pre-pass, `registerlabel`, `fullaccess` no-op, `/* */` stripping in data dialect, line-attached error messages; `inert/documented` classification for comment-only scripts | 2 | `aa.py`, `aa_program.py` | ~130 + 38 | case-18 | ready |
| WP-32 | addressless value-record demotion (simple + profile types) to non-actionable placeholder with named reason; children needing the base stay blocked | 2 | `compiler.py` entry policy, `table.py` kind | 74 | case-17 | ready |
| WP-33 | hex bit-pattern Float/Double (fixed-size raw pattern write, `struct` round-trip, dual guard changed together) | 2 | `compiler.py`, `engine.py` | 5 | case-17 | ready |
| WP-34 | diagnostics: missing-vs-ambiguous link target split, hex-string reason, AP-08.3/08.7 citation alignment | 2 | `compiler.py` | 0 (quality) | case-16/17 | ready |
| WP-35 | `dq`/`resb` operand-less reservation span: program-owned allocation only, must be written before publish, no cross-program access | 2 | `aa_program.py`, engine coordinator | ~405 | case-18 | ready |
| WP-36 | `aobscan`/`aobscanregion` staged under existing scan budget; `createthread` keeps capability gate with named reason; 3-arg `globalalloc(sym,size,$process)` accepted | 2 | `aa_program.py`, `compiler.py` scan policy | ~25 | case-18 | ready |
| WP-37 | Lua-owned symbol handover contract (unique external provider; reference allowed, foreign dealloc refused; ambiguity rule) | 3 | `lua_program.py`, `aa_program.py:883-895`, `compiler.py` provider map, coordinator teardown order | ~176 + 231 ambiguous | case-24 | design (root design note required first) |
| WP-38 | runtime dynamic address provider (plan-schema extension, provider-record contract, base re-resolution on activation + re-attach, UI marker) | 3 | plan schema, `validate_plan` (both), `engine.py`, trainer UI | 327 | case-21 | design |
| WP-39 | trainer-creator structured per-table inspection result (supported/blocked/top-reasons/warnings; file-level diagnostics for GC-T1…T4; API-boundary grouping) | 3 | `converter.py` GUI, plan diagnostics | UX | case-19 shapes | ready |
| WP-40 | record hotkey registration (first-wins + warning) + original-binding display | 3 | `engine.py`, `hotkey_model.py`, `ui.py` | UX (37 tables) | case-23 | ready (two sub-lanes: engine / UI) |
| WP-41 | table-Lua bootstrap phase 1 (per-table scope, read-only subset, named block reasons, trainer banner) | 3 | `lua_bootstrap.py`, `lua_host.py`, engine lifecycle | 49 tables' dependent records | case-22 | design (root design note required first) |
| WP-42 | embedded-Forms rendering (Ascii85 `TTrainerForm` decode + control binding) | deferred | trainer UI, table model | 10 tables (low priority) | case-25 | open (separate milestone; needs format investigation) |

Dependency constraints: WP-27 after WP-24 (same `_dropdown` function);
WP-37/38/41 gated by root-owned design notes (§3.3); Wave 2 lanes must not
touch `compiler.py` label-registry hunks concurrently with WP-28.

### 3.3 Design notes owed by root before implementation starts

| Note | For | Open questions |
| --- | --- | --- |
| Ownership-handover contract | WP-37 | exact `external_owned_providers` schema; ambiguity resolution (deterministic pick vs. named block); teardown-order proof plan |
| Dynamic-provider contract | WP-38 | plan schema field + versioning; invalidation of cached bases; re-attach semantics for saved ON-switches; UI marker contract |
| Table-Lua phase-1 scope | WP-41 | read-only API subset list; block-reason taxonomy; banner metadata location in plan |
| Duplicate-ID plan model | WP-25 | **decided 2026-10-13** (plan §10): keep-first is the plan entry, later duplicates dropped + one table warning; plan total = unique-ID count so gate:1 assertion holds; gate:1 count updated by root when case-19 is pinned |

## 4. Corpus cases (synthetic clean-room, `TableReferences/`)

Pinned and byte-verified (SHA-256 in `TableReferences/README.md`):

| Case | Origin shape | Status |
| --- | --- | --- |
| case-01 … case-14 | see `TableReferences/README.md` (WP-14: case-14 = PRAGMATA behaviour derivative) | pinned |

Planned for this cycle (land together with the owning WP; module token
`ct2synthNN.exe` per case; SHA-256 pinned on addition; added to
`tools/corpus_denominator/__main__.py` `PINNED` by root; gate:1 count
assertion updated accordingly):

| Case | Shape (anonymized) | WP | Status |
| --- | --- | --- | --- |
| case-15 | module & token shapes + offset arithmetic + expression forms (digit-leading module, `$process` scan, `@@:` globalalloc, `A:B`/`A::B` labels, `C00+58`-style offsets, cast/indirection record) | WP-19, 20, 21, 22, 23, 30 | planned |
| case-16 | linked dropdowns + separator rows (shared list w/ empty-value rows, linked bit-field + byte-array records incl. one wrong-length choice, one dangling link target) | WP-24, 27, 34 | planned |
| case-17 | template demotion & edge types (addressless simple + profile value rows, `ShowAsHex` string + float, custom type w/o definition) | WP-32, 33, A6/A8 | planned |
| case-18 | AA label & directive pack (positional `return:` in two scripts, alloc-only init + consumers, 2-arg `dealloc`, multi-token `registersymbol`, `registerlabel`, `fullaccess`, `/* */`, operand-less `dq`/`resb`, process-wide `aobscan`, 3-arg `globalalloc`) | WP-28, 29, 31, 35, 36 | planned |
| case-19 | table robustness (duplicate-ID pair, one a group with children; binary `CHEATENGINE\t` header file as a separate fixture) | WP-25, 39 | planned |
| case-20 | Lua directives & phase markers (`{$STRICT}` before `[ENABLE]`; unknown `{$bogus}`; `{$lua}` + preamble + in-block `[ENABLE]` + `{$asm}` + `[DISABLE]`; redundant `{$asm}`) | WP-26 | planned |
| case-21 | dynamic address provider (addressless header + Lua provider writing parent address, 2–3 relative children) | WP-38 | planned |
| case-22 | table-Lua bootstrap (table Lua global used by record Lua; top-level-write variant) | WP-41 | planned |
| case-23 | record hotkeys (F1 enable, F2 value op, one conflict pair) | WP-40 | planned |
| case-24 | Lua-owned symbol handover (mixed `{$lua}`/`{$asm}` record allocating + registering a symbol; foreign-dealloc variant as negative control) | WP-37 | planned |
| case-25 | embedded-Forms baseline (synthetic Ascii85 blob + 2 child elements; warning + `has_forms`) | WP-42 | planned (deferred) |

## 5. Measurement snapshot (update on every integration)

| Metric | Value | Run |
| --- | --- | --- |
| Pinned-corpus feature matrix | 42/42 covered, 7361/7361 action-weighted | `wp14-staged-20261011T093320Z` |
| Reference-corpus blocked entries | 21,852 / 117,019 (4 whole-table errors) | `ref-assessment` (2026-10-13 baseline) |
| AP-11 confirmed actions | 0 / 6011 | `wp14-staged-20261011T093320Z` |
| Latest build | `native-20261012T092729Z-2d8aaf12` (0.11) | in-build suite 2710/25 |
| Local dev suite | 2710 OK / 25 expected skips | `main` @ `ef668c1` |

Update protocol: after each merged WP — re-run the blocked catalog on the
scratch corpus, record the per-family delta in §2 status columns and here;
regenerate pinned-corpus artifacts with a fresh run id when a new case is
pinned; keep the two corpora's metrics separate (pinned corpus = feature
matrix/AP-11; reference corpus = closure progress).

## 6. Integration log (newest first)

| Date | Event | Evidence |
| --- | --- | --- |
| 2026-10-13 | Cycle kickoff committed (`native-0.12`): tracker + assessment + plan; CE 7.5 boundary wired into AGENTS.md / lane rules / plan index; case registry reconciled (case-15…case-25); WP-25 duplicate-ID plan model decided (keep-first, dropped duplicates + table warning, plan §10). Wave 1 lanes W1-C (WP-22/23), W1-D (WP-25), W1-E (WP-26) launched in disjoint worktrees `side/w1-c|w1-d|w1-e`; W1-A (WP-19/21/24) + W1-B (WP-20) queued (compiler.py overlap → sequential merges) | main @ `9c6a698`; lane branches `w1-c`/`w1-d`/`w1-e` cut from main |
| 2026-10-13 | Reference-corpus assessment closed: 4 lanes + root recompilation; consolidated assessment + closure plan + this tracker created; CE 7.5 behavior reference adopted (user decision) | `ref-assessment` catalog (21,852 / 117,019); lane reports in `reference-assessment/raw/` (local-only) |
