# Reference-Table Gap Assessment (151-table reference corpus)

Status: **2026-10-13** — consolidated from four read-only analysis lanes
(A: dropdowns/values, B: address expressions, C: AA grammar/symbols, D:
Lua/host/UX) plus root-owned recompilation and CE 7.5 source verification.
Raw lane reports stay local-only under `reference-assessment/raw/`
(gitignored); this document is the committed, consolidated assessment.

## 1. Scope and method

**Input corpus:** 151 `.CT` tables under the local-only folder
`C:\Users\xboxl\code\reference-table-input-do-not-add-to-git` (never added to
git; no raw table content is copied into this repository). A scratch copy
lives in `C:\Users\xboxl\AppData\Local\Temp\opencode\ref-corpus` for
re-runnable analysis.

**Ground truth:** per-table `compile_table()` through the shipped native
converter (dev venv Python), producing the blocked catalog
(`blocked-catalog.json`): every plan entry classified supported / staged /
blocked with its exact block reason, plus per-table `reason_counts`
(authoritative totals; the saved entry list is capped at 500/table and is
used for examples only).

**Machine-level totals (run `ref-assessment`, 2026-10-13):**

| Metric | Value |
| --- | ---: |
| Tables | 151 |
| Plan entries (compiler denominator) | 117,019 |
| Supported (incl. staged) | 95,167 |
| — of which staged | 46,987 |
| Blocked | 21,852 |
| Whole-table compile errors | 4 |
| Distinct block reasons | 725 |

Entry-count basis: the compiler plan (117,019) is the authoritative
denominator per `documentation/native-semantic-denominator.md`; a raw-XML
scan counts 117,648 `<CheatEntry>` nodes (includes entries in non-standard
sections).

**Behavior reference (2026-10-13 user decision):** the Cheat Engine 7.5
source tree at `C:\Users\xboxl\code\cheat-engine-7.5` is a
**behavior-reference only**. It may be read to understand how CE handles
edge cases; **no code is copied or derived from it** — every CT2Trainer
implementation stays clean-room. Verified claims below cite that source.

## 2. The four whole-table compile failures

One malformed record or table defect currently kills the entire table; the
whole table's records vanish from supported/blocked accounting.

| Table | Entries | Error | Root cause (verified) |
| --- | ---: | --- | --- |
| `AtomicHeart-Win64-Shipping.CT` | 20 | `NativeCompileError: Unsupported address expression: '"$process"'.` | `validate_plan` (`compiler.py:882-886`) re-validates scan modules without the `$process` special case that the compile path (`aa.py:205`) and `aa_program.py:326-328` already have. Consistency bug, not a missing feature. |
| `Cyberpunk2077.CT` | 349 | `AddressExpressionError: Invalid address expression near '@@'.` | (a) `global_alloc.py:149` classifies the NASM `@@:` cursor line as a named global label and feeds `@@` to `global_references` → `parse_expression`, which raises; (b) `AddressExpressionError` inherits `ValueError`, **not** `AAError`, so it escapes the per-entry catch at `compiler.py:619` and aborts the table. |
| `Octopath_Traveler-Win64-Shipping.CT` | 260 | `TableError: Duplicate CheatEntry ID: 1150.` | The source genuinely contains 24 distinct duplicated IDs (`1150-1152`, `4420-4430`, `7000`, `7010`, `7011`, `7020`, `7021`, `8013`, `8023`, `8033`, `8043`, `8053`). CE loads such tables — `TAddresslist.loadTableXMLFromNode` (`addresslist.pas:517-541`) creates one record per `<CheatEntry>` node with **no duplicate-ID check**; duplicates are separate addressable tree nodes. Native keys its maps by ID (`compiler.py:637`), so it must choose deterministically (recommended: keep first, block the duplicate, table-level warning). |
| `SuperMeatBoy.CT` | n/a (binary) | `TableError: Invalid CT XML: syntax error: line 1, column 0` | Legacy pre-XML binary table format (header `CHEATENGINE\t`, CE 5.x era, 10,328 bytes). Correctly refused; only the diagnostic should name the format. |

## 3. Master rollup — all 21,852 blocked entries

Deduplicated by first-matching reason family (compound reasons counted
once). Families are grouped by owning root cause.

| Entries | Family (block-reason marker) | Root-cause class |
| ---: | --- | --- |
| 12,876 | "other" (dominated by value-record/dropdown families, below) | mixed |
| 8,372 | `Required symbol has no unique supported provider: <sym>.` | **provider cascade** (§5) |
| 231 | `Symbol provider is ambiguous: <sym>.` | symbol-ownership design |
| 106 | `Lua/ASM delimiters must occupy standalone lines` | Lua directive whitelist (§4.4) |
| 54 | `Lua program phases are duplicated or out of order` | phase markers in explicit `{$lua}` (§4.4) |
| 52 | `Unsupported address expression: '<expr>'` | address-expression profile (§4.2) |
| 48 | `Unsupported AA directive: <name>` | AA dialect gaps (§4.3) |
| 26 | `Unexpected trailing address expression tokens` | token grammar (§4.2) |
| 25 | `Symbol must contain ASCII letters, digits or underscores` | symbol naming (§4.3) |
| 16 | `Invalid address expression near '<tok>'` | address-expression profile (§4.2) |
| 15 | `Enable section has no executable patch or data` | allocation-only / inert scripts (§4.3) |
| 12 | `Cannot register a symbol not owned by this program: <sym>` | Lua-owned symbol handover (§4.3) |
| 7 | `Cleanup may only release symbols/allocations owned by this program` | ownership (compound with 12) |
| 5 | `C-style comments are unsupported in the bounded AA dialect` | data-dialect comment stripping (§4.3) |
| 2 | `Global initialization requires one direct ENABLE cursor` | global-init profile (rare) |
| 2 | `Labels inside a global initializer are outside the direct literal profile` | global-init profile (rare) |
| 2 | `Malformed or empty directive arguments` | diagnostics |
| 1 | `Unsupported assembler directive: dq` | `dq`/`resb` reservation (§4.3) |

### 3.1 Dropdown / value-record families (Lane A, exact recompilation)

| Entries | Block reason | True sub-cause |
| ---: | --- | --- |
| 10,935 | `Dropdown contains an unsupported value expression.` | 10,859 linked-target lists with **empty-value separator rows** (METAPHOR v9: 4,416; P3R family: 2,129+2,138+2,138+38); 35 own-list section rows; 25 decimal-comma float literals (`0,5`); 12 `??` placeholders; 1 hex-styled list for a decimal type; 3 out-of-range linked choices |
| 1,215 | `Linked dropdowns for byte arrays and bit fields are unsupported.` | blanket `value_profile` guard at `compiler.py:132-133`; the engine write path (WP-15 bit-field writes, `parse_profile_value`) already accepts the exact choice formats found in the corpus — a missing-feature gap, not an engine limitation |
| 36 | `Dropdown link target is missing or ambiguous.` | all 36 are **missing** targets (dangling `DropDownListLink` labels; CE shows an empty dropdown); none ambiguous — keep fail-closed, sharpen the message |
| 23 | `Record has no implemented native action or address.` | addressless template/placeholder rows (UE5 "script templates" sections) — demote to non-actionable display placeholders |
| 51 | `Value record has no address expression.` | same family for profile value types (`Binary`, `Array of byte`, `String`) — same demotion fix |
| 15 | `Strings require literal text display` | `ShowAsHex="1"` string records (DS2: 9, Horizon ×2: 6) — byte-view of a text buffer; keep blocked, clearer reason (optional read-only hex view later) |
| 5 | `Hexadecimal floating-point bit patterns are unsupported.` | Float/Double `ShowAsHex` (trine4) — raw IEEE-754 bit pattern; cheap real feature (4/8-byte raw pattern write with `struct` round-trip) |
| 6 | `Custom value type '<t>' has no static definition … (AP-08.3)` | runtime-Lua custom types (RE2 `RE2_Hrs/Mins/Secs`); correct fail-closed; align the AP reference (compiler cites AP-08.3, runtime gate AP-08.7) |

### 3.2 Address-expression families (Lane B)

| Entries | Gap | Fix class |
| ---: | --- | --- |
| 20 (whole table) | `$process` rejected by `validate_plan` only | one-line consistency fix (mirror `aa.py:205`) |
| 349 (whole table) | `@@` cursor in `global_alloc` prep + error containment | accept `@@` cursor + per-entry catch of `AddressExpressionError`/`GlobalError` |
| 239 | pointer offsets must be bare hex literals | constant-fold hex arithmetic via the existing expression evaluator; normalize annotated hex (`20 (Offset of the name pointer)`); keep dotted-ident (18), cast/deref (2), symbol-expression (3) fail-closed or deferred |
| 10 (whole table) | module basenames starting with a digit (`20XX.exe+…`) | token grammar: add digit-leading `name.(exe\|dll)` alternative ordered before the bare-integer alternative |
| ~15 | `Class::Method` double-colon managed labels | grammar alias (`:` or `::`), resolution unchanged |
| 327 | relative addresses under addressless script-parent providers (Octopath2: 327 of 331) | **capability gap**: runtime dynamic address provider contract (provider record writes the parent address at activation via `Recorder.writeAddress`-style semantics); plan-schema + engine design |

Offset sub-form inventory (verified against the reference corpus, 600
non-bare `<Offset>` slots in 15 tables): constant arithmetic
(`C00+100`, `13A8+118`, `A0+4*4`, `433c+10c*4`, `30+30+30+30`); annotated
hex (`20 (Offset of the name pointer)`); dotted identifiers
(`GameEngine.GameInstance`, Callisto V1.1 / working.ct); cast+deref
(`(dword)[pInventoryItemResource+B8]*4`, Horizon pair); symbol expressions
(`[originalcode6_enable+3]`, SOTTR). CE 7.5 evaluation pipeline
(`TMemrecOffset.setOffsetText`, `MemoryRecordUnit.pas:631-696`): hex parse
(`ConvertHexStrToRealStr` `parsers.pas:377` → `StrToQWordEx`
`parsers.pas:248`) → symbol lookup → **Lua-expression fallback**
(`local memrec, address=...; return <offsettext>`); `(INT)/(FLOAT)/(DOUBLE)/(DOUBLE32L)/(DOUBLE32H)`
prefixes and character-pointer literals are also accepted. The working
published tables establish the target semantics as hex/decimal constant
**arithmetic** evaluation (the native `parse_expression` already implements
exactly this arithmetic; the gap is that `_offsets` uses a stricter
literal-only regex).

### 3.3 AA grammar / symbol families (Lane C)

| Entries | Gap | Notes |
| ---: | --- | --- |
| ~2,530 | positional `return:` label after AOB injection | single largest verified chain: P3Reload provider (id 1701013206) blocked on `return` → 2,483 downstream (11.4 % of all blocked). Bare labels defined outside an allocation are treated as external symbols by the table-wide label registry (`compiler.py:380-405`), which drops multi-definer names. CE scopes labels per script: the `labels` array is local to each `autoassemble2` call (`autoassembler.pas:1443-1452`); cross-script sharing is only via `registersymbol`/symbol handler. Fix: per-program label scoping; bare positional labels resolve against the program's own patch position (scan base + patch size); declared labels (`label(return)`) stay unconditionally local |
| ~540 | `alloc` rejected in data path + allocation-only init scripts | Shinkansen/Yooka-Laylee base-init shape: `registersymbol`+`alloc` only, no code → `Enable section has no executable patch or data` (`aa_program.py:778-779`); ~130-symbol init scripts (DeathStrandingDC) cascade 514 downstream |
| ~176 | Lua-allocated symbol ownership | DS2 `KeyHandlerThread`/`CameraHandlerThread` (12 direct) + ctts/re2 families: symbols allocated by table Lua (`allocateMemory`+`registerSymbol`) cannot be `registersymbol`'d by AA scripts (`aa_program.py:883-886`). Needs an explicit ownership-handover contract (unique external provider; no dealloc of foreign memory) |
| ~630 | bounded address-expression profile | cast+indirection chains (`(DWORD)[X+3]+X+7`, GhostOfTsushima 349 downstream; SandFall 21), `@`-anchored forms (Witcher3 ~168), managed-method addresses |
| ~405 | `dq`/`resb` uninitialized reservation | operand-less `dq` rejected (`aa_program.py:211`); Lust from Beyond id=5 single rejection blocks 392 downstream. Safe shape: reservation span inside a program-owned allocation, required to be written before publish |
| ~130 | small grammar items | 2-arg `dealloc(sym,size)` (8), multi-token `registersymbol` in the data-dialect pre-pass, dotted aobscan symbol names (5 — author quirk; keep fail-closed with targeted message), `registerlabel` (11 direct + 8 downstream), `fullaccess` no-op (1), `/* */` block comments in the data dialect (10 + 33 cascade; the program dialect already strips them), malformed-arg line attachment |
| ~20-30 | `aobscan`/`aobscanregion`/`createthread` | process-wide scans exist in the program dialect (`scan_process`/`scan_region`) but are refused by static-scan policy; `createthread` has a Stage-1 contract the grammar gate has not opened (deliberate capability gate — keep gated, name the gate in the block reason) |
| 38 | no-action / comment-only scripts | CE activates such records harmlessly (documentation rows); classify as `inert/documented` (reporting change first) — strict rule: only scripts whose entire body is comments/whitespace |
| ~5 | global-init profile residuals | `globalalloc(sym,size,$process)` 3-arg form (Resonance), label-based global initializers (SinkingCity) — accept the process-anchored 3-arg form; keep the direct-literal initializer profile bounded, name the offending label |

### 3.4 Lua / host / UX families (Lane D)

| Entries / scope | Gap | Notes |
| ---: | --- | --- |
| 106 | `{$STRICT}` & non-conditional `{$…}` directives rejected | whitelist is if/else/endif/define only (`aa_program.py:73-78`); the raise message ("delimiters must occupy standalone lines", `lua_program.py:144-148`) is misleading — the delimiter *does* occupy a standalone line. CE: `{$STRICT}` is a real directive (sets `strictmode`, `autoassembler.pas:1831`); `{$ccode}`/`{$luacode}` blocks are replaced in pass 1 (`:1798`). Corpus: 86 raw `{$STRICT}` occurrences; fix = no-op pass-through for harmless directives + accurate named error for unknown ones |
| 54 | `[ENABLE]`/`[DISABLE]` not recognized inside explicit `{$lua}` blocks | the phase header is only honored when `implicit_lua` (`lua_program.py:289`); an explicitly terminated block lexes the marker as Lua code → later `[DISABLE]` triggers the phase-order raise (`:336-340`). CE 7.5 **splits phases on the raw text before Lua expansion** (`autoassemble` → `getEnableOrDisableScript` `autoassembler.pas:4584/4588`, then `autoassemble2` → `luacode` `:1797`); pre-`[ENABLE]` text runs in both phases. Fix: treat an exact phase-marker line as a structural boundary even inside an explicit Lua block; close the Lua chunk at the marker and route the text per phase |
| 7 | redundant `{$asm}` rejected | no-op mode setter in CE (CE blanks stray `{$ASM}` lines, `autoassembler.pas:1820-1822`); accept as no-op |
| 4 whole tables | G4a `validate_plan` `$process`, G4b `@@` containment, G4c duplicate IDs, G4d binary CT | see §2 |
| all failing tables | trainer-creator UI surfaces failure as one bare messagebox; plan warnings (table-Lua, omitted sections, hotkeys metadata-only — `compiler.py:724-734`) are never displayed | structured per-table inspection result `{supported, blocked, top_reasons[], warnings[]}` + file-level diagnostics for the four hard failure classes |
| 49 tables | table `<LuaScript>` not executed on load (read-only replay only, `lua_bootstrap.py`) | largest single behavioral gap in the Lua cluster: record Lua that depends on table-Lua globals fails at activation. Phase 1: execute the read-only subset in a per-table bootstrap scope; writes/callbacks/unsupported APIs block activation with a named reason |
| per API | Lua host API surface below corpus usage (Forms API, debugger API, `createMemoryRecord`, address-list mutation) | declared profile boundary; fail-closed per API is consistent; creator UI should group blocked records by missing API so the boundary reads as one decision |
| 37 tables / 164 entries / 247 hotkeys | record hotkeys: model exists (`hotkey_model.py`), nothing registered or displayed | engine registration (conflict policy first-wins + warning) + trainer UI display of original bindings; the two sub-lanes (display vs registration) are independent |
| 10 tables | embedded `<Forms>` ignored (warning only) | 7 single Ascii85 `TTrainerForm` blobs (opaque Delphi form data) + 24 child elements; keep fail-closed; surface the warning prominently; rendering is a separate milestone (needs the CE form binary format) |
| 5,179 | description-only records / group headers (5,105 headers + 74 leaves) | verified OK — headings, not errors; polish only (visual distinction, expand/collapse) |

### 3.5 Provider cascade (8,372 + 231) — not an independent root fix

`Required symbol has no unique supported provider` entries are value
records whose base symbol is provided by a record that is **itself blocked**
in another family. Top chains (verified):

| Blocked | Provider | Upstream root cause |
| ---: | --- | --- |
| 2,483 | P3Reload `GlobalWorkPtr` | positional `return:` label (§3.3) |
| 1,250 + 540 + 481 | AtomicHeart v1.2 `Character_Pointer`/`Esau_base`/`Character2_Pointer` | ambiguous symbol (two scripts register the same name) + legacy module names |
| ~349 | GhostOfTsushima `pplayeraddress` | cast+indirection address expression (§3.3) |
| ~168 | Witcher3 `mouse_ovr`/`loot_ptr`/`player_ptr` | `@`-anchored expressions |
| ~392 | Lust from Beyond `_playerbase` | `dq`/`resb` rejection |
| ~220 + ~230 | Horizon ×2 / DS2 `dsplayerentity` | Lua/ASM delimiter + phase clusters (§3.4) |
| ~514 | DeathStrandingDC base script | `alloc` allocation-only (§3.3) |
| 227 | (39 tables) | no provider record in the table at all (may be table-Lua-provided; regex matching caveat) |

Handling: report with per-provider evidence; they unblock automatically when
the upstream WPs land. The 231 ambiguous-provider entries are a
symbol-ownership design question (unique-provider rule vs. explicit
ambiguity resolution) tracked together with the ownership-handover WP.

## 4. True gap vs. malformed vs. scope boundary — classification

| Class | Items | Disposition |
| --- | --- | --- |
| **True product gaps (fix this cycle)** | `$process` in `validate_plan`; `@@` containment; offset constant-folding; digit-leading module names; `::` managed labels; separator-row dropdown policy; profile-aware linked dropdowns; positional `return` scoping; allocation-only profile; Lua-owned symbol handover; bounded address-expression profile; `dq`/`resb` spans; small grammar items; Lua directive/phase handling; addressless-value demotion; hex-float bit patterns | WPs in `plans/reference-closure-continuation.md` |
| **Capability design (later milestone)** | runtime dynamic address provider (Octopath2, 327); table-Lua execution on load (49 tables); embedded Forms rendering; `createthread` opening | design-first WPs |
| **Malformed / authoring defects (keep fail-closed)** | dotted-ident offsets (18), cast/deref offsets (2), symbol-expression offsets (3), SOTTR addressless trees (10), empty-address template records after demotion, comma-decimal dropdown values (25), `??` placeholders (12), hex-styled choice lists (1), out-of-range choices (3), dotted aobscan symbol names (5), string junk in Witcher3 expressions (4), hex-float bit patterns *if* kept (see hex-float WP), unterminated block comment (1), duplicate-ID *re-keying* | current reasons are correct; message polish where noted |
| **Scope boundaries (declared, no change)** | Forms API / debugger / `createMemoryRecord` Lua APIs; binary CT tables; non-XML content | named fail-closed errors; creator-UI surfacing |

## 5. Quantified impact summary (if all in-cycle WPs land)

| Fix | Entries unblocked | Share of 21,852 |
| --- | ---: | ---: |
| Separator-row dropdown policy | 10,894 | 49.9 % |
| Positional `return` + per-program label scoping | ~2,530 | 11.6 % |
| Lua directive/phase handling (incl. ~522 cascade) | ~690 | 3.2 % |
| Profile-aware linked dropdowns | up to 1,215 | 5.6 % |
| Bounded address-expression profile (incl. ~540 cascade) | ~630 | 2.9 % |
| `alloc` allocation-only profile (incl. ~514 cascade) | ~540 | 2.5 % |
| `dq`/`resb` reservation spans (incl. 392 cascade) | ~405 | 1.9 % |
| Dynamic address provider | 327 | 1.5 % |
| Offset constant-folding | 216 | 1.0 % |
| Whole tables (AtomicHeart, Cyberpunk, Octopath, 20XX) | 20 + 349 + 260 + 10 | 3.3 % |
| Lua-owned symbol handover (incl. 120 cascade) | ~176 | 0.8 % |
| Addressless-value demotion | 74 | 0.3 % |
| Small grammar items + aobscan/createthread + global-init | ~160 | 0.7 % |
| Hex-float bit patterns | 5 | 0.02 % |

Best case: **~18,500 of 21,852 blocked entries (≈ 85 %)** clear in this
campaign cycle (sum of the per-fix rows above, ≈ 18,501; plus the 231
ambiguous-provider entries once the ownership-handover WP lands ≈
18,700 / 86 %); the residue is the deliberately kept
malformed/authoring defects plus the declared scope boundaries, each
with a named, actionable block reason.

## 6. CE 7.5 behavior-reference notes (verified this session)

Read-only consultation of `C:\Users\xboxl\code\cheat-engine-7.5` to pin the
*behavior* the reference tables rely on (no code copied; clean-room
re-implementation required):

| Behavior | Evidence location (CE 7.5) | Implication for CT2Trainer |
| --- | --- | --- |
| Phase split happens on raw script text **before** `{$lua}` expansion | `autoassemble` → `getEnableOrDisableScript` (`autoassembler.pas:4584/4588`) precedes `autoassemble2`; `luacode` inside `autoassemble2` (`:1797`) | `[ENABLE]`/`[DISABLE]` are structural even inside an explicit `{$lua}` block; pre-`[ENABLE]` Lua runs in both phases |
| `{$STRICT}` is a recognized directive (sets strict mode); `{$ccode}`/`{$luacode}` blocks are replaced in pass 1 | `autoassembler.pas:1798, 1831` | harmless standalone directives are no-op pass-throughs in the native profile; unknown `{$…}` gets an accurate named error |
| Stray redundant `{$ASM}` lines are blanked (no-op) | `autoassembler.pas:1820-1822` | redundant mode setters accepted as no-ops |
| Duplicate `<CheatEntry>` IDs load without any duplicate check; each node becomes its own record | `TAddresslist.loadTableXMLFromNode` (`addresslist.pas:517-541`); `TMemoryRecord.setXMLnode` (`MemoryRecordUnit.pas:1313-1315`) | CE keeps both entries; native must choose deterministically (keep-first + block duplicate + table warning) because plan maps are keyed by ID |
| Pointer offset text is stored verbatim and evaluated at update time: hex → symbol lookup → Lua-expression fallback; typed prefixes `(INT)/(FLOAT)/(DOUBLE)/(DOUBLE32L)/(DOUBLE32H)` and character-pointer literals supported | `TMemrecOffset.setOffsetText` (`MemoryRecordUnit.pas:631-696`); `ConvertHexStrToRealStr` (`parsers.pas:377-555`); `StrToQWordEx` (`parsers.pas:248-267`) | native offset slots accept constant hex/decimal arithmetic (bounded, pure-integer AST); symbol-typed and cast offsets stay fail-closed with precise reasons |
| AA labels are scoped per script: the label table is local to each `autoassemble2` call; cross-script name sharing happens only through the symbol handler (`registersymbol`) | `tlabel`/`labels` local to `autoassemble2` (`autoassembler.pas:1443-1452`) | per-program label scoping in the native compiler; the table-wide registry is only the explicit symbol channel |
| Runtime pointer chase consumes integer offsets only (hex evaluated earlier) | `getPointerAddress` (`pointerparser.pas:26-49`) | constant folding belongs in the compiler, not the runtime chase loop |

## 7. Caveats

1. **Catalog cap:** `blocked_entries` per table is capped at 500; the two
   truncated tables (P3Reload 2,483 cascade; Oregon) had their upstream
   families verified by direct recompilation instead. `reason_counts` are
   complete and authoritative.
2. **Provider matching:** cascade attribution used regex over raw script
   text (`registersymbol(`/`aobscan*(`/`alloc(`/…); one false positive found
   (commented-out `registerSymbol` in a `--` Lua comment).
3. **`{$STRICT}` semantics:** CE strict mode changes assembler error
   behaviour; the native profile is fail-closed by design, so "accept and
   ignore" is a documented scope decision, not an emulation of CE strict
   mode.
4. **Duplicate-ID keep-first:** verify no cross-references (group
   membership, `by_id` lookups, saved selections) depend on the dropped
   duplicate; keep-first minimizes reference breakage (engine indexes by
   ID; selection persistence uses IDs).
5. **Raw delimiter counts** (e.g. 86 `{$STRICT}`) are text-level
   case-insensitive counts including tokens in comments/strings; the
   authoritative blocked-record counts are the catalog values (106/54/7).
6. **CE 7.5 source** is a behavior reference only (2026-10-13 user
   decision); it is not an implementation input and no part of it is
   reproduced in this repository.

## 8. Derivative corpus cases (anonymized) — registry

The following synthetic clean-room cases (added to `TableReferences/` with
their implementing WPs; numbering continues after `case-14`) recreate each
root-cause shape without any raw table content:

| Case | Shape (synthetic, owned token `ct2synthNN.exe`) | Covers WPs |
| --- | --- | --- |
| `case-15` | module & token shapes + offset arithmetic + expression forms: digit-leading secondary module in addresses; `aobscanmodule(sym, $process, …)`; globalalloc with `@@:` cursor lines + staged readmem pair; single- and double-colon managed labels; `C00+58`/`A0+4*4`/`1594+8+118`-style offset slots; cast + nested-indirection address (WP-30 part) | WP-19, WP-20, WP-21, WP-22, WP-23, WP-30 |
| `case-16` | linked dropdowns + separator rows: shared 200-choice list with empty-value separator rows + linked records; own-list section rows; comma-decimal float choice (stays blocked); `??` placeholder (stays blocked); linked bit-field record (`BitStart=5,BitLength=1`, 0/1 list) and linked byte-array record incl. one wrong-length choice; one dangling link target (missing-vs-ambiguous diagnostic) | WP-24, WP-27, WP-34 |
| `case-17` | template demotion & edge types: addressless Byte/Binary/4-Bytes template rows (with one relative child that stays blocked); String `ShowAsHex` (stays blocked); Float `ShowAsHex` (supported after WP-33); Custom type without static definition (stays blocked) | WP-32, WP-33, WP-34 |
| `case-18` | AA label & directive pack: positional `return:` after an AOB injection (two scripts, both with their own `return:`); allocation-only init script feeding consumer value records; 2-arg `dealloc`, multi-token `registersymbol`, `registerlabel`, `fullaccess` no-op, `/* */` comments; operand-less `dq`/`resb` reservation written later; process-wide `aobscan`/`aobscanregion` + `createthread` gate; 3-arg `globalalloc(sym,size,$process)` | WP-28, WP-29, WP-31, WP-35, WP-36 |
| `case-19` | table robustness: two entries sharing an ID (one a group with children) → keep-first + warning; byte file with binary `CHEATENGINE\t` header → named legacy-binary error (shapes reused by the WP-39 inspection UX) | WP-25, WP-39 |
| `case-20` | Lua directives & phase markers: `{$STRICT}` before `[ENABLE]`; unknown `{$bogus}` (named fail-closed); `{$lua}` + syntaxcheck preamble + in-block `[ENABLE]` + `{$asm}` + `[DISABLE]`; redundant `{$asm}` mid-script | WP-26 |
| `case-21` | dynamic address provider: addressless group header + Lua provider writing the parent address at `[ENABLE]` (nilled at `[DISABLE]`) + 2–3 relative children | WP-38 |
| `case-22` | table-Lua bootstrap: table Lua defining a global used by record Lua (activates after WP-41); table Lua with top-level write → loads, activation blocked with named reason | WP-41 |
| `case-23` | record hotkeys: F1 enable, F2 value-op, one conflict pair → metadata displayed, supported keys registered, conflict warned | WP-40 |
| `case-24` | Lua-owned symbol handover: mixed `{$lua}`/`{$asm}` record allocating + registering a symbol, AA phase consuming it; variant deallocating the foreign symbol in its own DISABLE (stays blocked) | WP-37 |
| `case-25` | embedded-Forms baseline: synthetic Ascii85 blob + 2 child elements; warning + `has_forms` | WP-42 |

Each case lands with its WP (fixture + dedicated test file + plan
assertions), is pinned by SHA-256 in `TableReferences/README.md`, added to
`tools/corpus_denominator/__main__.py` (`PINNED`), and re-runs the
deterministic measurement chain.
