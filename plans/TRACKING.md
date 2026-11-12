# CT2Trainer — Central Gap & Goal Tracking

For a concise explanation of these measurements and the overall goal,
see [Current status](../STATUS.md). Update it with this tracker whenever
new evidence changes a count, gate, build or next step.

## Current decision (2026-10-20)

The active objective is [100% support of the local reference tables](reference-table-100-roadmap.md).
The 0.16 Wave-4 package set is complete. The 42/42 feature matrix proves
coverage of the 30 pinned **synthetic** cases, not the 151 original-table
paths (143 distinct hashes). The latest local-only original-table catalog
has 2,698 blocked of 117,624 plan entries and one legacy-binary load
error. The figures below describing earlier waves and old `ready` package
states are historical baselines; use the goals and queue immediately below
for active work. No original table contents enter the repository.

### Active goals

| ID | Outcome | State | Exit evidence |
| --- | --- | --- | --- |
| GOAL-8 | 100% reference-table load and semantic support | open | RT-1 through RT-5 in the roadmap; all 151 paths/143 distinct hashes inventoried, all intended actions executable, no unexplained blocked or staged rows, no hidden table-level construct. |
| GOAL-9 | 100% original-table observed behavior | open | RT-6; per-table game-build/runtime evidence for distinct behavior contracts. Unavailable game targets remain explicitly unverified. |
| GOAL-10 | Clean Windows and Steam Deck acceptance | open | Both platform protocols recorded with exact build, hashes, setup and result; only then reassess `runtime_unverified`. |
| GOAL-11 | Clean-room redistributable release | active guard | RT-7; independent implementation, no CE code/binaries/original tables in shipped ZIPs, offline build proof. |

GOAL-1 is complete only for the synthetic feature matrix; GOAL-2 remains
open and its old 85% estimate is superseded by the 100% reference-table
target. GOAL-3/AP-11 (0/6,143 confirmed) is a separate game campaign.
GOAL-4/5/6 remain open; GOAL-7 is historical release work.

### First packages

| Package | Owner | State | Next concrete output |
| --- | --- | --- | --- |
| RT-1 full-corpus rebaseline | root | done (2026-10-21) | Frozen manifest `gap_inventory/reference-manifest.json` (151 paths, 143 hashes, exact EXE bindings); catalog re-run on the 0.16 source (`blocked-catalog-rt1`) identical per table to the 2026-10-20 run (2,698 / 117,624, 1 legacy-binary load error); stale 15/27-table prose in `gap-report.json`/`feature-coverage.json` repaired at the tool source and regenerated under the pinned run id. |
| RT-2 residual attribution | root | done (2026-10-21) | All 2,698 blocked rows traced to an upstream terminal cause (lane final2 run; root re-verified every class sum and per-table sum in both directions and independently re-ran the corrected UNDEFINED-split logic against the local corpus): 1,931 cascade rows = 1,304 undefined-symbol (963 AA-hidden in-table registrations, 110 Lua-runtime, 91 no-registration, 128 legacy built-in, 12 API export) + 624 duplicate-provider cascades + 3 wildcard-cleanup; 767 direct rows in 27 classes. Per-class testable contract, risk, expected delta and the RT-4 package split (RT-4.1 820 / RT-4.2 1,085 / RT-4.3 452 / RT-4.4 65 / RT-4.5 57 / RT-4.6 219; sums to 2,698) recorded in the roadmap's RT-2 root-cause map; CE 7.5 behavior probes (dropdown overflow truncates at SetValue, bare module names without .exe fail in CE too, IL2CPP Type:Member pipe-server-only, BaseAddress has no CE built-in handling, usemono is a newer-CE directive) recorded with source citations; the lane final report (2026-10-21 21:14) is the authoritative record, with verified per-family roots for the 963 AA-hidden rows and seven caveats. |
| RT-3 legacy binary load | lane `native-rt3` | done (2026-10-23) | Clean-room parser `src/ct2trainer/legacy_ct.py` for the CE 5.x-era pre-XML binary format (true 11-byte `CHEATENGINE` magic — byte 12 is the version-DWORD LSB; format versions 6-9 verified, >9 warns as assumed unchanged, <6 refused as too old; bounded named `LegacyCTError` refusals for truncation/corrupt magic/implausible counts and lengths); `read_table` dispatches magic-matching files to the parser and everything else to the unchanged XML path; the converted standard-XML document flows through the unchanged tested XML pipeline (`compile_table` consumes `Table.converted_xml`; source identity and the plan `table_sha256` stay pinned to the original binary bytes, matching the reference manifest; record IDs synthesized in document order); branch `native-rt3` merged to `main` 2026-10-23; full suite on `main` 3,450 OK / 25 expected skips; catalog remeasure (run `blocked-catalog-rt3`) 151/151 load (previous one legacy-binary load error cleared), 117,624 -> 117,634 total, 115,766 -> 115,776 supported (the 10 `SuperMeatBoy` records), staged unchanged 59,642, blocked unchanged 1,858, all other 150 tables byte-identical per-table counts — zero regressions. |
| RT-4 high-volume semantics | root | done (RT-4.1 2026-10-22, RT-4.4 2026-10-23, RT-4.6 2026-10-24, RT-4.5 2026-10-24, RT-4.3 2026-10-26, RT-4.2 2026-10-27) | RT-4.1 symbol provider fidelity landed on 2026-10-22 (branch `native-rt4-1` merged to `main`): keep-first duplicate-provider policy (CE `dupIgnore` alignment), `label()` duplicate-name tolerance, wildcard-cleanup scoping; nine focused modules 167 OK, full suite 3,415 OK / 25 expected skips; catalog remeasure (run `blocked-catalog-rt41`) 2,698 -> 1,858 blocked of 117,624 (net -840: 842 unblocked — all of R1 (624), R2 (3), O2 (186), 2 of 4 O16, plus 47 dup-rooted R3 rows; 2 explained Cyberpunk shared-global regressions per the pinned `test_compatible_duplicate_declarers_share_without_ambiguous_external_admission` contract; zero unexplained supported regressions; case-28 plan state unchanged 10/9/9/1). RT-4.4 value semantics landed on 2026-10-23 (branch `native-rt4-4` merged to `main`): O6/O8 dropdown width + expression choices per the CE SetValue conclusions (truncating integer writes, strict `[...]` expression bracket contract, alternate-base hex literals as a documented clean-room extension, unparseable choices become display rows on read-only dropdowns), O7 ShowAsHex strings staged as byte_array value profiles, O26 empty/placeholder-only read-only dropdowns staged as display-only views; O11 custom-type gate kept by design; 18 new tests in tests/test_native_value_semantics.py plus pin updates; full suite on main after the merge 3,471 OK / 25 expected skips; catalog remeasure (run `blocked-catalog-rt44`) 1,858 -> 1,807 blocked of 117,634 (net -51: O6 30, O7 8, O8 13; zero newly blocked; 8 rows reason-changed onto pre-existing symbol-provider blocks). RT-4.6 input legacy & authoring gaps landed on 2026-10-24 (branch `native-rt4-6` merged to `main`): actionable per-symbol 'not registered anywhere in this table' report with raw-source registration survey (R5/R6 closure), x87 `st`/`st(N)` FPU-operand tokenizer fold (CE Assemblerunit.pas:3283-3291; `st(8)`+ stays fail-closed), optional user-symbol import (`compile_table(user_symbols=...)`, `load_user_symbols`, CLI `--user-symbols`, plan field `user_symbols`, engine seeds UDS then user symbols, forged-map refusals in both plan validators); 53 new tests, full suite on main after the merge 3,532 OK / 25 expected skips; catalog remeasure (run `blocked-catalog-rt46`) 1,807 -> 1,778 blocked of 117,634 (net -29: LFD `st` 1 + Witcher3 4.02HF1/4.03 x14 each behind the now-supported 'Activate Player Scripts' provider; zero newly blocked; 218 rows reason-changed generic -> actionable per-symbol report, all still blocked; known root-owned NASM 3.02 FSTP-fpureg defect documented). RT-4.5 AA directive & script coverage landed on 2026-10-24 (branch `native-rt4-5` merged to `main` after the RT-4.6 merge): usemono() parity-scope refusal in both envelope halves (O15), CE 7.5 dealloc name-list semantics (O12), three-segment managed labels (O18), global DISABLE reset regions + empty-consumer program round trip (O19), symbol-only luaCall envelopes with two-pass release (O20), label-before-data refusal kept (O21) and external-owner suffix on named symbol-handover refusals (O5); 30 new tests, full suite on main after the merge 3,562 OK / 25 expected skips; catalog remeasure (run `blocked-catalog-rt45main`) 1,778 -> 1,743 blocked of 117,634 (net -35: RDR2 1, Resonance 1, SOTTR 2, Shinkansen Sunless Sea 1, Subnautica_e67616 28, TheSinkingCity 2; zero newly blocked; 7 rows reason-changed, all still blocked and explained - 4 usemono rows onto the parity-scope refusal, Subnautica id=89 onto the ownership gate, Sunless Skies id=29 onto trailing tokens, TheSinkingCity id=258084 onto the changed-reinitialization refusal). Remaining packages in suggested order: RT-4.3 452, RT-4.2 1,085 last; each lands with synthetic case, full suite, catalog delta with zero unexplained supported regressions, and a remeasure. RT-4.3 address expression & identifier dialect landed on 2026-10-26 (branch `native-rt4-3` merged to `main` after a root rebase onto `29adebb`; four conflicts resolved: main's bounded `{1,2}` managed-label tail from RT-4.5 (O18) kept, the lane's hyphen-module and digit-leading-symbol atoms kept, test pins aligned to the merged unregistered-symbol report): O1 relative-address skip-fold over addressless script/value ancestors plus O9 runtime-base marker staging on group headings (engine `set_dynamic_address` restricted to a supported addressless `kind=script` writer), O3 pointer-offset expression slots staged verbatim and resolved against the live symbol table at activation, O10 identifier dialect (digit-leading and dot-bearing symbol names per the CE `label()` contract; hyphen module basenames as one atom while `.exe/.dll`-qualified export atoms stay whole; all-hex names stay refused), O23 quoted-atom refusal naming the offending token, O27/O4 Type:Member managed labels resolved through the injected IL2CPP resolver with per-label named refusals, O13 directive-aware string data bytes (db one ANSI byte per char, dw UTF-16LE words of any length, dd/dq packed little-endian zero-padded); 27 new tests (dedicated tests/test_native_address_expression_dialect.py +20 plus pins in five existing test files); full suite on main after the merge 3,613 OK / 25 expected skips (clean run exit 0); catalog remeasure (run `blocked-catalog-rt43-main`) 1,743 -> 1,351 blocked of 117,634 (net -392: O1 195, O3 51, O4/O27 trailing-token and Type:Member atoms 38, O9 8, O13 5, O10 direct 5 plus 90 dependent rows whose symbol/provider-lookup terminal reason was cleared by the grammar; staged 59,735 -> 59,868; zero newly blocked; 12 rows reason-changed, all still blocked and explained; residual O1/O9 rows keep their reason behind addressless runtime-script ancestors - RT-4.2 territory). RT-4.2 runtime provider model landed on 2026-10-27 (branch `native-rt4-2` merged to `main`, merge `bb86983`): R3 keep-first duplicate-provider scope fallback (a blocked kept provider no longer strands dependents; the first still-supported candidate resolves the symbol; single-candidate and shared-global branches keep their classic refusals), R4 mixed-dialect release evidence (AA `unregistersymbol(` release proof from `{$asm}` DISABLE parts per the CE 7.5 split-on-commas/whitespace contract with `*`-wildcard and scalar-tail exclusions; Lua `unregisterSymbol` stays strict-pair per the gettop==1 handler), R7 bounded API-export registry (bare `call GetAsyncKeyState` / `FindWindowA` supported with the exact `api_exports` plan marker, forged-marker refusals in both plan validators, link-time resolution against the target's live export table with fail-closed absent-export refusal before any write); dedicated tests/test_native_rt42_runtime_provider.py +21 plus the R7 pin migration in tests/test_native_undefined_provider_report.py; full suite on main after the merge 3,692 OK / 25 expected skips; catalog remeasure (run `blocked-catalog-rt42-main`) 1,351 -> 1,053 blocked of 117,634 (net -298: R4 Lua runtime symbol providers 286 now staged, R7 GetAsyncKeyState bare-call rows 12 supported, R3 keep-first scope fallback catalog-neutral, plus 5 previously supported-plain rows re-staged through the now-supported runtime providers; staged 59,868 -> 60,161; zero newly blocked; 28 rows reason-changed, all still blocked and explained). RT-4 is complete; remaining roadmap work is RT-5 items A-E, RT-6 and RT-7. |
| RT-5 runtime trainer parity | root | done (2026-10-31: inventory 2026-10-23; items F+G 2026-10-26; items A+C 2026-10-28; item C2 2026-10-29; item D 2026-10-29; items B+E 2026-10-31 — all inventory items A–G landed; final remeasure `blocked-catalog-020-rt5-be`: 1,053 blocked of 117,809, 116,756 supported incl. 175 code-patch entries, zero newly blocked at every step) | Full API/construct inventory landed as `documentation/rt5-api-inventory.md` (2026-10-23): 394 distinct Lua call names cross-classified (61 CE globals, 36 CE object methods, 28 stdlib, 269 table-local); 20 hosted CE globals, 41 named-refusal gaps split 14 game-facing vs 27 pure-UI no-effect; table-level construct census with per-construct scope decisions (CheatCodes code patches 22 tables/175 entries, embedded .lua loader chain in 4 tables, onOpenProcess/onTableLoad callback dispatch, `Structures` unreferenced, `LastState`/sounds/signatures no-effect); remaining RT-5 implementation items A-G queued in the doc section 9 after the RT-4 lanes. Visual CE UI is outside scope. Item G (`createThread`/`threadWait` backend decision, O22) landed 2026-10-26 (lane `native-rt5-g`, merge `2de9c0e`): decision recorded — option (2), capability gate stays, no thread backend ships this milestone (bounded owned-thread backend awaits a root design review: lifecycle, debug-event ownership, join semantics, exact disable teardown, journal receipt); byte-stable five-stage fail-closed pins in `tests/test_native_rt5_thread_gate.py` (+17 tests: focused 17 OK; main suite 3,648 OK / 25 expected skips after the merge); census re-derived from launch base `blocked-catalog-rt43-main`: exactly 2 O22 rows (Witcher3 4.02HF1_G25v2 + 4.03_G25v2, id 192, "Call Function") and 77 first-word `createThread` usages across 18 tables split into 26 AA directive lines in 8 tables (gate-governed) and 51 Lua-context lines in 11 tables (`lua_host` cooperative workers, separate family, not O22-gated), zero first-word `threadWait` lines; tests only, zero catalog movement (remeasure `blocked-catalog-rt5g-main`: 1,351 blocked of 117,634, zero delta). Item F (no-effect register ratification) landed 2026-10-26 (lane `native-rt5-f`, merge `966fccd`): `tests/test_native_rt5_no_effect_register.py` +22 tests pin the section-8 register as an enforced byte-stable contract (26 CE UI globals keep the exact `Unsupported CE Lua API: <name>` refusal with zero target side effects; section-7.3 object-method register pinned per surface; table-level Structures/Signature/SignedHash/PublicKey/Forms/Files families byte-exact warnings + sorted `ignored_sections`, plan-inert; LastState/RealAddress/Color/Comments silent; GroupHeader supported; ActivateSound/DeactivateSound hotkey children ignored; usemono() exact composite reason); tests-only, zero catalog movement (remeasure `blocked-catalog-rt5f-main`: 1,351 blocked of 117,634, zero delta). Item A (embedded `<Files>` extraction + `findTableFile`/`readStringLocal`) landed 2026-10-28 (lane `native-rt5-a`, merge `479977c`): new `src/ct2trainer/native/embedded_files.py` (CE dual-branch codec — exact `Encoding="Ascii85"` = CE-alphabet Ascii85 + raw deflate + 4-byte-LE size prefix; any other/missing value = CE hex branch, hex -> raw deflate read-until-EOF without size prefix, per `luafile.pas::createFromXML`; 4 MiB per-file transport-tracking bound, 16 MiB table total), fail-closed table-load decode (`_parse_embedded_files`, named `TableError`), plan projection `embedded_files` (casefold-sorted, additive, re-validated by both plan validators, schema-2 only), engine registry (`_embedded_files`/`_embedded_by_name`, case-sensitive exact-name, first-occurrence-wins on tolerated duplicates), Lua surface: `findTableFile`/`FindTableFile` (nil when absent, dual access shapes), `readStringLocal` (token-based, strict UTF-8; deviations pinned: omitted/negative maxsize returns full content, no NUL truncation), `stringstream.*` (per-scope registry, 256-object / 16 MiB bounds), `createTableFile`/`tablefile.delete` fail-closed refusals, stringlist `Text` getter/setter (CRLF-to-LF positional split, empty lines kept) + gmatch bug fix, `load`/`loadstring` string-chunk-only compat wrapper; `tests/test_native_rt5_embedded_files.py` +53 (12-case refusal matrix, P5 + RiftApart end-to-end shapes, codec/plan/table-load contracts); full main suite after the merge 3,745 OK / 25 expected skips (baseline 3,692); catalog remeasure (run `blocked-catalog-rt5a-main`): zero delta vs `blocked-catalog-rt42-main` (151/151 load, 117,634 total, 116,581 supported (60,161 staged), 1,053 blocked, 0 compile errors, 0 newly blocked, 0 reason-changed); the 9 reference files with non-empty `<Files>` (7 distinct games) gain `embedded_files` in their plans, zero blocking-status movement. Item C (bounded process-info Lua API family) landed on 2026-10-28 (lane `native-rt5-c`, commit `0167825`): 11 APIs under the clean-room single-target model (getProcessIDFromProcessName returns the attached pid on plan-process match, else 0; getProcessList single-entry pid->name map; getAutoAttachList inert per-scope singleton stringlist; getOpenedProcessID alias; getSettings inert object; integerToUserData identity; targetIs64Bit pointer width; enumModules single-module answer; disassemble bounded iced in the CE line shape; stringlist_add ordinal; getCEVersion pinned '7.5'), item-A-style allowlist wiring (table-scope read-only names + record-scope functions + syntax-check reads), `tests/test_native_rt5_process_info.py` +23 (14-case refusal matrix, byte-exact disassemble lines, 32-bit behavior on pointer_size=4, zero memory writes on all refusals); full main suite after the merge 3,790 OK / 25 expected skips (baseline 3,767); catalog remeasure (run `blocked-catalog-rt5c-main`): zero delta vs `blocked-catalog-rt5a-main` (151/151 load, 117,634 total, 116,581 supported (60,161 staged), 1,053 blocked, 0 compile errors, 0 newly blocked, 0 reason-changed); 44 of 151 tables reference at least one item-C API; no plan fields, no engine path changes. Item C2 (dynamic addresslist records + custom AA directives) landed on 2026-10-29 (lane `native-rt5-c2`, commit `dbfdcc2`, merge `dde9f04`): createMemoryRecord session journal (synthetic IDs >= 2**31, never persisted, cleared on target exit/close, bounded 4096) via AddressList / getAddressList() / built-in AddressList index; CE MemoryRecord runtime surface (Description/Type/Address with verbatim expression text/Script/Parent cycle + self-parent refusal + grandchild promotion/Child[i] 0-based/Offset + OffsetText[i] bounded writes/Count/Index/OffsetCount/isDynamic/Value vtByte..vtDouble read-write/inert display keys); journal + plan-record OnActivate/OnDeactivate as 'ct2fn:<n>' tokens fired from the owning host with stale-scope containment; plan display mutations session-stored (plan untouched); getCEVersion now the number 7.5 (CE LuaHandler pushnumber parity; item-C string pin superseded); addresslist lookups getMemoryRecord (int = flat 0-based position, str = casefolded description, absent -> nil) + getMemoryRecordByID numeric-string coercion + casefolded ByDescription + Count/MemoryRecord[i] OOB nil + inert selection; registerAutoAssemblerCommand/unregisterAutoAssemblerCommand table-scope custom AA directives (built-in names refused, registry dies with table scope, expansion in prepare_program after nested-assembly inlining, strict no-op without registry, revalidation through validate/preflight/dry_link/link); `tests/test_native_rt5_dynamic_records.py` +27 plus pin updates (test_native_rt5_process_info number pin, test_native_lua record.set helper no-op, test_native_rt5_no_effect_register getMemoryRecord now supported, test_native_table_lua_bootstrap record.set engine refusal, test_native_aa_literals signature); full main suite after the merge 3,817 OK / 25 expected skips (baseline 3,790); catalog remeasure (run `blocked-catalog-rt5c2-main`): zero delta vs `blocked-catalog-rt5c-main` (151/151 load, 117,634 total, 116,581 supported (60,161 staged), 1,053 blocked, 0 compile errors, 0 newly blocked, 0 reason-changed). Item D (`onOpenProcess`/`onTableLoad` callback dispatch) landed 2026-10-29 (lane `native-rt5-d`, commit `fb1253b`, merge `9294bb8`): after a clean table-Lua bootstrap the trainer fires the table's CE callbacks on the table-scope host in the CE sequence (onOpenProcess with the attached target PID as a Lua number, then onTableLoad with the Lua literal false - documented bounded deviation: the once-per-attach bootstrap has no before-load phase); each callback in one pcall-wrapped chunk with the argument injected as a literal (no string injection; the chunk uses only stdlib, no table-scope allowlist change), 'absent'/'ok'/'error: <msg>' -> no event / table-callback / table-callback-error, throwing callback contained with plan['table_lua'] byte-identical (the clean bootstrap stays clean for the dependent record scripts), the second callback still dispatches, idempotent per confirmed attach with re-attach re-fire on the fresh scope, refused or failed bootstraps skip the dispatch; `tests/test_native_rt5_table_callbacks.py` +9; full main suite after the merge 3,826 OK / 25 expected skips (baseline 3,817); catalog remeasure (run `blocked-catalog-rt5d-main`): zero delta vs `blocked-catalog-rt5c2-main` (151/151 load, 117,634 total, 116,581 supported (60,161 staged), 1,053 blocked, 0 compile errors, 0 newly blocked, 0 reason-changed). Item B (CheatCodes code-patch plan path) landed 2026-10-31 (lane `native-0.20-rt5-b`, commit `3f1cce3`, merge `9ef4a74`): fail-closed per-entry `<CheatCodes>/<CodeEntry>` parse (whole-byte hex codec with `<Byte>` child and text fallback, 4096-entry section bound, per-entry named drop warnings, `GroupHeader` rows become supported headings — zero in the corpus), `code_patch` plan records with synthetic IDs at 2**32+ (above the C2 dynamic-record journal range 2**31+1..2**31+4096; documented deviation from the task's 2**31 base), CE code-list address forms with a compile-time static symbol-free expression gate, `CheatCodes` added to the interpreted-section whitelist, both plan validators re-deriving the canonical shape with forged-entry refusals, engine lifecycle with named refusals (`code-patch-already-active`, `code-patch-target-changed` zero-write refusal, `code-patch-restore-mismatch` refusal + engine block; disable restores the captured-at-enable original — documented superset of CE), executable pages through the verified coordinator hook journal, data pages through the ordinary byte transaction, standard wish persistence with re-attach re-enable and close-time restore, `_check_patches` skip, UI switch rows with the `code` chip; `tests/test_native_rt5_code_patch.py` +26; full main suite after the merge 3,880 OK / 26 expected skips (baseline 3,854); catalog remeasure on main (run `blocked-catalog-020-rt5-be`): 117,634 -> 117,809 total, 116,581 -> 116,756 supported (+175, all 22-table CodeEntry records), 1,053 blocked and 60,161 staged unchanged, 0 load errors, zero newly blocked, zero reason changes. Item E (`messageDialog` decision) landed 2026-10-31 (branch `native-0.20-rt5-be`, commit `a5d0a2f`, merge `b8bb4ee`): safe logged no-op returning 0 (mbOK, truthy in Lua) with the CE 7.5 argument shapes (message / title+message / dialogtype / buttons), nil argument tolerance (corpus table Lua passes undefined button constants as nil), `message-dialog` debug event, both spellings in record + table scope (`TABLE_LUA_READ_ONLY_NAMES`, 47 corpus table-Lua call sites); `tests/test_native_rt5_message_dialog.py` +22 plus pin updates; full main suite after the merge 3,902 OK / 26 expected skips; catalog remeasure (run `blocked-catalog-rt5e-iteme`): zero delta vs `blocked-catalog-019-field`. With items B and E, every RT-5 inventory item (A, B, C, C2, D, E, F, G) has landed — RT-5 is complete; next work is RT-6 (validation) and RT-7 (release gate). |

No active worker is implied by `ready` or `design`. WP-19…58 below are
completed historical waves except WP-42; its embedded Forms rendering is
outside the requested visual UI scope unless a form control mediates a
game-facing action.

## Current measurement

- Synthetic pinned corpus: 30 tables, 6,143 expected AP-11 actions; feature
  matrix 42/42 and action weight 7,475/7,475 (run
  `w4b4-case30-20261020081722Z`). This does not measure original-table
  parity.
- Local original reference catalog: 151 paths, 143 distinct hashes, all
  151 load, 116,756 supported (60,161 staged) and 1,053 blocked of
  117,809 plan entries; zero load errors (0.21 RT-5 item B/E remeasure,
  2026-10-31, run `blocked-catalog-020-rt5-be`, frozen manifest
  `gap_inventory/reference-manifest.json`; +175 supported vs
  `blocked-catalog-020-icons` — the 175 `CodeEntry` records of the 22
  CheatCodes tables now `code_patch` plan rows, zero newly blocked,
  zero reason changes; item E `messageDialog` no-op is a
  zero-delta runtime host behavior, run `blocked-catalog-rt5e-iteme`;
  previous 0.20 branding cycle remeasure 2026-10-30, run
  `blocked-catalog-020-icons`; zero delta vs
  `blocked-catalog-019-field`; previous 0.19 field-fix cycle remeasure
  2026-10-30, run `blocked-catalog-019-field`; zero delta vs
  `blocked-catalog-rt5d-main`; previous RT-5 item D remeasure
  2026-10-29, run `blocked-catalog-rt5d-main`; zero delta vs
  `blocked-catalog-rt5c2-main`; previous RT-5 item C2 remeasure
  2026-10-29 run `blocked-catalog-rt5c2-main`: zero delta vs
  `blocked-catalog-rt5c-main`; previous RT-5 item C remeasure 2026-10-28
  run `blocked-catalog-rt5c-main`: zero delta vs
  `blocked-catalog-rt5a-main`; previous RT-5 item A remeasure 2026-10-28
  run `blocked-catalog-rt5a-main`: zero delta vs
  `blocked-catalog-rt42-main`; previous RT-4.2 remeasure 2026-10-27 run
  `blocked-catalog-rt42-main`: net -298 vs
  `blocked-catalog-rt43-main`: R4 Lua runtime symbol providers 286 now
  staged (DS2 118, HorizonForbiddenWest 82 per copy, ForgottonAnne
  dMoveValueMultiplier 2, Witcher3 bIsLevel 1 per copy), R7
  GetAsyncKeyState bare-call rows 12 supported with the api_exports
  plan marker (ForgottonAnne 7, trine2 3, Witcher3 1 per copy), R3
  keep-first scope fallback catalog-neutral, plus 5 previously
  supported-plain rows re-staged through the now-supported runtime
  providers; zero newly blocked; 28 rows reason-changed, all still
  blocked and explained; previous: 116,283 supported (59,868 staged) /
  1,351 blocked, RT-4.3 remeasure 2026-10-26 run
  `blocked-catalog-rt43-main` (net -392 vs
  `blocked-catalog-rt45main`: O1 relative-address skip-fold 195, O3
  pointer-offset expression slots 51, O4/O27 trailing-token and
  Type:Member atoms 38 (incl. the Sunless Skies O27 row), O9
  runtime-base staging 8, O13 indirect data 5, O10 identifier-dialect
  direct 5 plus 90 dependent rows whose symbol/provider-lookup terminal
  reason was cleared by the new grammar; zero newly blocked; 12 rows
  reason-changed, all still blocked and explained; previous:
  115,891 supported (59,735 staged) / 1,743 blocked, RT-4.5 remeasure
  2026-10-24 run `blocked-catalog-rt45main` (net -35 vs
  `blocked-catalog-rt46`: O12/O5 aobscanregion + cleanup-ownership rows
  and O19/O20/O21 global-init rows cleared (Subnautica_e67616 28, SOTTR
  2, TheSinkingCity 2, RDR2 1, Resonance 1, Shinkansen Sunless Sea 1),
  zero newly blocked, 7 rows reason-changed, all still blocked and
  explained; previous: 115,856 supported (59,709 staged) / 1,778
  blocked, RT-4.6 remeasure 2026-10-24 run `blocked-catalog-rt46`;
  further previous: 115,827 supported (59,683 staged) / 1,807 blocked,
  RT-4.4 remeasure 2026-10-23 run `blocked-catalog-rt44`; further
  previous: 115,776 supported (59,642 staged) / 1,858 blocked, RT-3
  remeasure 2026-10-23 run `blocked-catalog-rt3`; further previous:
  115,766 supported (59,642 staged) / 1,858 blocked of 117,624 with one
  legacy-binary load error, RT-4.1 remeasure 2026-10-22 run
  `blocked-catalog-rt41`; further previous: 114,926 supported
  (58,950 staged) / 2,698 blocked, post-Wave-4 catalog 2026-10-20,
  reproduced per table by the RT-1 re-run on the 0.16 source,
  2026-10-21).
- Local original reference catalog re-verified after the trainer UI
  feature change (2026-10-24, run `blocked-catalog-ui-scripts`):
  per-table identical to `blocked-catalog-rt45main` - 151/151 load,
  117,634 total, 115,891 supported (59,735 staged), 1,743 blocked,
  zero compile errors, zero newly blocked/unblocked, zero
  reason-changed rows (UI-only change, zero catalog effect).
- AP-11 confirmed effects: 0/6,143. Windows and real Deck acceptance
  remain open; `runtime_unverified` remains set.
- 0.21 Master Trainer (2026-10-31, branch
  `native-0.20-master-trainer`, merged `main` @ `9a725a8`; released in
  build `native-20261031T211046Z-14707e12` - in-build suite 4,044 OK
  / 30 expected skips, fully green at the canonical path):
  one long-lived trainer window that indexes a folder of `.ct` tables
  (sub-folders included; incremental `(size, mtime_ns)` fingerprint
  index, sha256-equal refresh keeps derived process names,
  checksum-bound JSON in the state home, foreign schema/root and
  tampered checksums refused) and waits for a bound game process
  (Toolhelp32 on Windows, `/proc/<pid>/exe` on Linux/SteamOS); unique
  match auto-loads, multi-table match opens the picker, trainer mode
  is the unchanged `TrainerWindow` with an optional `master_back`
  button; per-table on/off persistence rides the existing engine state
  store; all waiting-mode logic is a pure, UI-free orchestrator
  (fail-closed loop guard, open-choice stability); `ct2trainer native
  master [FOLDER]` CLI; user-provided `Master_Trainer` icon set
  (`window_icon_path("master")`). 141 new tests (index 18,
  process-watch 35, orchestrator 42, UI 46) + the three-kind icon
  contract; four source bugs found and fixed during test-lane
  development (process-watch import depth, picker tuple-padding,
  recovery-decline fail-closed, `set_folder` import). Full dev suite
  on the 0.21 build: 4,044 OK / 30 expected skips, 0 failures -
  fully green at the canonical build path (the dev-suite run had 3
  known path-dependent baseline-reproducibility test failures that
  pass at the canonical build path). Catalog: unchanged (no
  plan-builder code touched; zero Master Trainer effect vs
  `blocked-catalog-020-rt5-be`).
- 0.22 FO4 field-fix cycle (2026-11-01, branch
  `native-0.21-fo4-rearm`, merged `main` @ `a12a0b6`, commit
  `5704fd2`): bounded automatic re-arm of ScanMiss enable failures -
  arming from manual toggle and wish restore (fresh budget), executor
  and `try_again` consume attempts; 30 s x 10 attempts
  (`REARM_INTERVAL_SECONDS` / `REARM_MAX_ATTEMPTS` module constants);
  budget reset per confirmed (re-)attach; armed set + `enable_failures`
  survive detach; value-read / non-ScanMiss failures never armed
  (plain-failed contract unchanged); manual "Try again" row action
  (3-tuple context-menu item with disabled state, budget reset after
  exhaustion) and top-level "Re-attach" header action
  (`_detach_current_target` extracted from the target-exited poll
  branch; named refusals while closed/blocked/busy); JSONL events
  rearm-scheduled/-attempt{-attempt,max,result}/-succeeded/-exhausted
  + reattach-requested/-done{pid}/-failed{reason} (deduped per request
  across the five unattached attach-failure points)/-detached;
  `tests/test_native_rearm.py` +17 (10 engine + 7 UI/pure). Driver:
  FO4 0.20 field test 2026-10-31 (Steam Deck / Proton) - 6/8 wish
  restores ScanMiss while the game was still loading. Full main suite
  4,061 OK / 30 expected skips (canonical path); catalog zero delta
  `blocked-catalog-022-rearm` (151/151 loaded, 0 compile errors,
  117,809 total / 116,756 supported / 60,161 staged / 1,053 blocked /
  0 load errors). Field-test findings recorded from the FO4 (0.20)
  and SC2 (0.19, 3 sessions) debug logs (local-only, never committed):
  SC2 hotkey-bridge defects - unguarded `RegisterHotKeyW` missing-export
  path (raw AttributeError where the named HotkeyRegistrationError was
  designed), hotkey failure hard-blocking the engine incl. close(),
  deterministic close-timeout + AV in the bridge message loop (Windows
  x2 + Deck x1), transient-read PatchConflict (Win32 299), state-lock
  first-restart refusal on "absent" observations; SC2 hotkey-bridge
  fixes deferred to the next field-fix cycle. The 0.22 build is cut
  from this content.
- 0.23 Master Trainer roadmap complete (2026-11-01, branch
  `native-0.23-master-roadmap`; lane `lane-mt8-frozen-entry` merge
  `deed3c5`, lane `lane-mt67-sidecar-deck` merge `cee58b7`, root
  integration `b2d0344`; MT-9 load-gate branch
  `native-0.23-load-gate` merge `98a9226`; main @ `6e3ec98`): MT-8 frozen entry
  `tools/native_master.py` -> `CT2Trainer-Master.exe` (windowed,
  lazy `master_ui` import so `--help` + named exit-2 refusals need
  no tkinter; CLI mirrors the `master` subcommand; `build()`
  freezes it after the converter with the `Master_Trainer.ico`, no
  `CT2BASE1` marker, `inventory()` scan, `payload-inventory.json` /
  `build.json` outputs / portable ZIP entry - the Master Trainer is
  now part of every build; `scripts/Build-Native.ps1` unchanged);
  MT-6 `settings_sidecar.py` (`MasterSettingsStore` keyed by the
  table content sha256, never path; `<state home>/settings/<sha>.ct2trainer.json`;
  `load_for` (document, reasons) contract - absent file normal,
  `SettingsRejection` reasons displayable, structural
  `SettingsError` named; `save_for` document-derived known ids +
  named `nothing to persist`; UI restore-on-load with visible named
  refusal, save-on-close; on/off wish persistence stays on the
  engine state store); MT-7 `steamdeck_route.py` (documented-route
  surface, NOT a Linux attach backend: `attach_gate` /
  `require_engine_attach` / `route_text`; named
  `DeckAttachUnavailableError` with the Proton-wrapped standalone
  CT2Trainer Windows trainer EXE route; gate before any engine
  creation; permanent waiting-view route hint on non-Windows; the
  real Deck protocol run with exact build hashes stays root/user
  field work); waiting-view observability (metadata line - table
  counts / bound names / scan time / state home; live "Running now"
  line with PIDs; running/PID tree-row markers; `TickOutcome.running`
  live bound-process list on every tick path); ask-on-first-start
  table-folder parameter (`master_state.py`, `master-settings.json`
  checksum-bound under the state home; explicit folder argument
  always wins + becomes the new persisted folder; stale stored
  folder -> picker); MT-9 `table_gate.py` (load-time compatibility +
  size re-proof of the table file against its index entry at the
  moment the load is requested: missing / not-a-regular-file /
  stat-or-read failure / empty / over the 32 MiB load limit
  (33,554,432 bytes) / changed since the last scan (named stale
  refusal, Rescan re-arms; keeps the MT-6 sidecar sha keying
  consistent) / not loadable by the tested `read_table` parser
  (malformed XML, DTD/entity input, unparseable legacy binary) /
  changed during analysis; stable named codes + displayable detail,
  cheapest-first; the default plan compiler raises
  `TableLoadGateRefusal` so a load failure is graceful even when the
  target process was found: named dialog + status line, fail-closed
  loop guard records the exact (name, PID) pair, no hot-retry,
  Rescan / Retry re-arm, no picker re-issue for a failed pair; +22
  tests: 16 gate + 2 orchestrator + 4 UI); same-day field fixes
  merged after the MT-9 merge: placeholder headings no longer create
  plan-level symbol dependencies (`28c9b57`, +10 tests) and the SC2
  hotkey-bridge field fix from the 0.22.1 lane (T1 named
  missing-export guard, T2 engine containment of bridge faults, T3
  loop-thread close protocol, T7 persistence ordering; merge
  `4e9b95b`, +11 tests). No new trainer functionality (wrapper
  around the tested engine). +115 tests (72 roadmap + 22 MT-9 + 10
  placeholder + 11 hotkey); full main suite 4,176 OK / 30 expected
  skips (canonical path, 2026-11-01). Catalog zero delta on all
  three remeasures (`blocked-catalog-023-master-roadmap` @
  `b2d0344`, `blocked-catalog-023-load-gate` @ `98a9226`,
  `blocked-catalog-023-field-fixes` @ `4e9b95b`: 151/151 loaded, 0
  compile errors, 117,809 total / 116,756 supported / 60,161 staged
  / 1,053 blocked / 0 load errors; per-table count and reason
  changes: 0). The 0.23 build was cut from this content set: run
  `native-20261101T145310Z-a160bae4` (in-build suite 4,176 OK / 30
  expected skips, `ce_inputs: []`, source ZIP sha256
  `3360cab031cb1334dda71bb02a511170a9a70d1f583b5a8721624f46e24da464`
  14,291,040 bytes, portable ZIP sha256
  `eec023ba09e8fcb80608736896f0477f4a783034046e6ad67514e96ed0a2905b`
  49,609,916 bytes).
- 0.24 trainer tick sounds (2026-11-01, user field request; branch
  `native-0.24-trainer-sounds`, full main suite 4,193 OK / 30 expected
  skips): the generated trainer now plays the tick sounds of the
  original native trainer generator's character - a distinct double
  tick on a confirmed (re-)attach to the game process and high/low
  single ticks on every confirmed on/off toggle of an item (manual row
  switch, group heading toggle, hotkey-dispatched activation toggles -
  CE parity: the original generated trainer sounds on every toggle,
  not only UI taps). Behavior reference (read-only, never copied): CE
  7.5's native trainer generator ships two built-in tick sounds
  (`Sounds.RC` -> `tick1.wav` / `tick2.wav`, `BUILDIN_ACTIVATE` /
  `BUILDIN_DEACTIVATE` RCDATA; ~28 ms, 8-bit unsigned mono, 11025 Hz,
  ~4.4 kHz activate / ~3.8 kHz deactivate, Win32 winmm `PlaySound`
  `SND_MEMORY | SND_ASYNC`); the reference corpus carries no
  table-embedded audio, so that built-in pair is the original sound
  set. Clean-room: deterministic in-code synthesis in the same format
  and pitch character, no CE asset bytes. New
  `src/ct2trainer/native/trainer_sounds.py` (tick synthesis,
  module-cached buffers, best-effort named-result playback that never
  raises), `ui.py` rewired (old 880/440 Hz sine helper removed; row
  switch + group heading toggle + the attach-success transition in
  `TrainerWindow.poll()` all play the ticks; the attach tick plays
  exactly once per (re-)attach, failed attach attempts stay silent),
  `engine.py` surfaces confirmed hotkey activation toggles through
  `TrainerEngine.pop_hotkey_ui_toggles()` (value-action hotkeys are
  not recorded). New `tests/test_native_trainer_sounds.py` +21
  (supersedes `tests/test_native_ui_tone.py`, 4 tests, removed).
  Catalog remeasure `blocked-catalog-024-sounds`: zero delta vs
  `blocked-catalog-023-field-fixes` (151/151 loaded, 117,809 total /
  116,756 supported / 60,161 staged / 1,053 blocked / 0 load errors;
  per-table changes 0).
  Build `native-20261102T102029Z-fe358e35` (2026-11-02, cut from
  `main` @ `a2777ed`): in-build suite 4,193 OK / 30 expected skips,
  `ce_inputs: []`, `runtime_unverified` deliberately kept per gate;
  source ZIP `CT2Trainer-0.24-source.zip` sha256
  `dfdd8cfcca90a2789bf544d8f8de4e34941067feeb2b32ce8d550f98e5bc4eb6`
  (14,298,696 bytes), portable ZIP
  `CT2Trainer-0.24-windows-portable.zip` sha256
  `12262cf16e906c3811ade0a8c582b7a1057c834a3110aff004dfd13b3067e7ab`
  (49,618,009 bytes); frozen `CT2Trainer-Master.exe` sha256
  `5f3a66400c2c1775e6fc50ad6bbbc36aa8a6bcf8b58fe56507117dc33683494d`
  (16,896,995 bytes) in the run folder, the payload inventory and
  the portable ZIP.
- 0.25 Master Trainer user control (2026-11-02, user request;
  root-direct on `main`, VERSION 0.25 + CHANGELOG entry in the same
  change; full main suite 4,259 OK / 30 expected skips): the Master
  Trainer gains explicit user control over which table loads and
  which process attaches, plus a detach / user-attach hold. The
  feature set was evaluated against online all-in-one trainer front
  ends (OpenForge (openforge-aio), the CE 7.5 process picker as the
  local read-only behavior reference, LaunchForge / auto-update
  loaders) and recorded in `master_trainer/ROADMAP.md` ("Online
  feature evaluation (2026-11-02)"): adopted MT-10/11/12;
  deliberately deferred (documented) global per-feature hotkeys,
  auto-update (offline/hash-verified build policy) and concurrent
  multi-table sessions (documented single-session model). MT-10
  explicit table load (waiting-view "Load table" header button +
  per-row "Load this table" context menu; the table loads even while
  the bound process is not running yet - the plan compiles
  statically, the engine waits for the process to start; the last
  explicitly loaded table persists in `master-settings.json` schema
  2 `last_table` and is visible in the metadata line;
  `orchestrator.request_load()` stable named refusals
  not-in-index / table-unreadable / no-process-binding /
  process-snapshot-failed - a refused load shows a named dialog +
  status line and never crashes; an explicit load bypasses the
  auto-load loop guard, but a failed explicit load still records the
  ordinary (name, PID) suppression). MT-11 process selection +
  persisted attach mode (new `process_picker.py` pure decision
  layer: `candidate_processes`, `attach_decision` -> attach-direct /
  pick / wait, `make_pinned_memory_factory` - the injected factory
  honors the session PID pin, self-clears the pin once that PID
  exits, falls back to the ordinary smallest-PID name-based attach;
  modes "auto" default legacy behavior - no picker, smallest PID -
  and "ask" - the process picker, one row per running candidate
  name+PID, shown for every attach incl. a single candidate; the
  "Attach: auto/ask" toggle persists the mode in
  `master-settings.json` schema 2, schema-1 documents promote on
  load with documented defaults last_table=null,
  attach_mode="auto"; cancel semantics per origin: auto-load pick
  defers the exact (name, PID) pair (Retry load re-arms), table
  choice defers like "Not now", explicit load returns to the waiting
  status, attach after detach stays paused). MT-12 detach / user
  attach (engine `pause_attach()` / `resume_attach()` /
  `attach_paused` - while paused the poll attach branch is gated:
  status "Detached; waiting for user attach", no attach attempts,
  session state/journals/wishes untouched, debug events
  attach-paused/attach-resumed, pausing refused with a named error
  while closed/blocked/busy; "Detach"/"Attach" header button in
  Master mode only, standalone trainer header byte-identical,
  `TrainerWindow` optional `detach_cb`; on "Attach": "ask" mode with
  running candidates opens the process picker (origin "attach") and
  the chosen PID pins the session, "auto" mode simply resumes the
  ordinary wait; a target exit while attached is unaffected).
  Test-harness hardening (test-only, no product code change): new
  `tests/native_tk_teardown.py` with `force_root_release()` -
  deterministic Tk-root teardown on the creator thread (destroy +
  drop named test-side references + forced main-thread gc.collect),
  applied in all 7 UI test modules (17 root creations); removes the
  intermittent `Tcl_AsyncDelete: async handler deleted by the wrong
  thread` abort of the 0.25 full-suite non-verbose runs
  (2026-11-02) - mechanism verified against the CPython 3.12
  tkinter source + faulthandler dump: the Tk root/interpreter
  reference cycle survives destroy() until a cyclic GC on whichever
  thread allocates finalizes the Tcl interpreter, and a
  worker-thread GC finalization aborts Tcl off the creator thread
  (two non-verbose full-suite runs aborted at ~71% with exit 1 and
  no summary; the verbose full run completed green; a middle-set
  repro did not reproduce; a clean-tree 0.24 @ `aba8b65` full run
  had no Tcl fatal). In-build reliability fix (first 0.25 in-build
  suite run `native-20261102T181843Z-ddfb63f0`, 2026-11-02, exposed
  it: the `run_master` cancel test read the machine's real state
  home - the in-build suite runs without the LOCALAPPDATA isolation
  of local dev runs - and on a field-tested box with a stored
  `last_folder` took the stored-folder reuse path with the mocked
  `tk.Tk`; the test now uses an isolated state home, a new
  deterministic test covers the reuse path, and the waiting-view
  status variable plus the table-picker selection variable in
  `master_ui.py` carry an explicit master (the window root) instead
  of the tkinter default-root lifecycle). +66 tests
  (`tests/test_native_master_process_picker.py`
  16, `tests/test_native_master_explicit_load.py` 13,
  `tests/test_native_attach_pause.py` 5,
  `tests/test_native_master_ui_mt12.py` 24, +7 schema-2 tests in
  `tests/test_native_master_state.py`, +1 state-home isolation test
  in `tests/test_native_master_ui.py`). Catalog remeasure
  `blocked-catalog-025-master-ui` (chunked 64x3 audit over the 151
  reference tables, 2026-11-02): 151/151 loaded, 0 load errors,
  117,809 total / 116,756 supported / 60,161 staged / 103,607
  actionable / 12,974 headings / 1,053 blocked - zero delta vs
  `blocked-catalog-024-sounds` (per-table count/reason/sha changes:
  0); feature matrix unchanged (42/42, 7,475/7,475 over
  `w4b4-case30-20261020081722Z`); AP-11 0/6,143.
- 0.26 Master Trainer waiting-view usability MT-13/14/15 (2026-11-03,
  root-direct on `main`; user request 2026-11-02/03, online-evaluated
  in `master_trainer/ROADMAP.md`, "0.26 waiting-view usability") +
  the live-target takeover field fix. MT-13: the new pure decision
  layer `table_filter.py` (`filter_tables` - empty/whitespace query =
  the identity, input order preserved, otherwise a casefolded
  substring over the table's relative path AND any bound process
  name; `sort_tables` - modes name/process/status, the casefolded
  relative path is the universal tie-breaker, unbound tables sort
  last in process mode, unknown mode raises `ValueError`); the
  waiting view renders `filter_tables(sort_tables(index.tables(),
  mode), query)`; row identity stays the relative path; the load
  picker and the auto-load path keep the full index; filter/sort are
  session-only (survive the trainer round-trip, never persisted).
  MT-14: double-click / Return / KP_Enter load the selected row
  through the MT-10 explicit-load path; "/" focuses the filter from
  anywhere in the waiting view (a no-op in trainer mode); Esc
  clears it. MT-15: `master-settings.json` schema 2 -> 3
  (`recent_tables`, most recent first, capped at ten, `{"path",
  "at"}` with the persisted UTC timestamp; schema-1/2 documents
  promote on load, a schema-2 document carrying the field is
  refused as an unknown field), `MasterApp.remember_recent_table`
  (prepend / dedup / cap / persist) at all three successful load
  points, meta line `recent: a, b, c (N more)`, the "Recent:
  <path>" one-click load button, tree Size / Modified / Last-used
  columns, window 1160x600 / minsize 900x420. Live-target takeover
  field fix: stale-lock recovery attaches to the still-running game
  behind one user-confirmed prompt when the owner is proven dead in
  both observations and only target-side identities remain unproven
  (state archived byte-for-byte; saved wishes re-applied - code-
  patch adopt idempotent, AOB ScanMiss named scan errors + bounded
  re-arm); unprovable/live owner, foreign artifact or any extra
  reason keeps the strict refusal. Regression fixes: `_meta_text()`
  re-gained its `state: <home>` line; the schema-3 round-trip,
  stored-folder and rescan tests updated to the new payload / 7
  columns. +61 tests (`test_native_master_table_filter.py` 17,
  `test_native_master_recent.py` 13, `test_native_master_ui_mt13.py`
  12, `test_native_live_target_takeover.py` +19 incl. updates).
  Full main suite 4,320 OK / 30 expected skips. Catalog remeasure
  `blocked-catalog-026-master-ui` (chunked 64x3 audit over the 151
  reference tables, 2026-11-03): 151/151 loaded, 0 load errors,
  117,809 total / 116,756 supported / 60,161 staged / 103,607
  actionable / 12,974 headings / 1,053 blocked - zero delta vs
  `blocked-catalog-026-live-target` (per-table count/reason/sha
  changes: 0); feature matrix unchanged (42/42, 7,475/7,475 over
  `w4b4-case30-20261020081722Z`); AP-11 0/6,143. Build
  `native-20261103T112811Z-59a6b3d5` cut from `main` @ `c114ec2`
  (2026-11-03): in-build suite 4,320 OK / 30 expected skips,
  `ce_inputs: []`, `runtime_unverified` deliberately kept per gate;
  source ZIP `CT2Trainer-0.26-source.zip` sha256
  `3d62f80cdfb95d8439d4a2f2150002976795faad313fa75d47aeb4fb92bb49bd`
  (14,348,462 bytes), portable ZIP
  `CT2Trainer-0.26-windows-portable.zip` sha256
  `49be1d286999ed175737edb073c5ab83533c40cccc7e636685a256a0b07004b3`
  (49,653,968 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `895f937ed5c228c09b97edba28aa9dc4ad228abd58585f73080f40ab265bc031`,
  16,925,677 bytes, ships next to the converter).
- 0.27 Master Trainer waiting-view settings persistence MT-16 +
  process-grouped waiting view MT-17 (2026-11-03, root-direct on
  `main`; online-evaluated in `master_trainer/ROADMAP.md`, "0.27
  waiting-view settings + process groups"). MT-16:
  `master-settings.json` schema 3 -> 4 (`view_filter` - the raw
  filter entry text, at most `VIEW_FILTER_MAX` = 200 characters,
  "" = no filter; `view_sort` - one of the table_filter sort
  modes; `view_mode` - "list" flat rows / "process" grouped by
  bound process name); schema-1/2/3 documents promote on load with
  the documented defaults ("" / "name" / "list"), a schema-3
  document carrying a view_* field is refused as an unknown field;
  the format-level constants live in `master_state` (the
  attach-mode pattern) and a test pins the mirror against the pure
  layer; `MasterApp.set_view_settings(filter_query, sort_mode,
  view_mode)` validates with named `ValueError`s and re-persists
  immediately; the window restores all three from the persisted
  document at construction and every UI change point re-persists
  (filter `<KeyRelease>`, sort cycle, view cycle, Esc clear).
  MT-17: the pure `table_filter.group_tables_by_process` reshaping
  of the already-sorted-and-filtered row set (never adds or drops
  tables: one group per casefolded bound process name, a
  multi-bound table once in EACH bound group, the unbound tables
  under "(no process binding)" last, within-group input order
  kept); the "View: list/process" cycle button between the sort
  button and the filter entry (persisted through MT-16); the tree
  (`show="headings"`) renders the group label + "N table(s)" count
  in values[0] of the parent row; group rows are display-only -
  `_is_table_row` gates the double-click, the Enter selection and
  the row context menu, the children load through the ordinary
  MT-10 path. +22 tests (`test_native_master_state.py` +4,
  `test_native_master_table_filter.py` +8,
  `tests/test_native_master_ui_mt16.py` new +10). Full main suite
  4,342 OK / 30 expected skips. Catalog remeasure
  `blocked-catalog-027-view` (chunked 64x3 audit over the 151
  reference tables, 2026-11-03): 151/151 loaded, 0 load errors,
  117,809 total / 116,756 supported / 60,161 staged / 103,607
  actionable / 12,974 headings / 1,053 blocked - zero delta vs
  `blocked-catalog-026-master-ui` (per-table count/reason/sha
  changes: 0); feature matrix unchanged (42/42, 7,475/7,475 over
  `w4b4-case30-20261020081722Z`); AP-11 0/6,143. The 0.27 build
  `native-20261103T145543Z-b29b3688` cut from `main` @ `8aa0815`
  (2026-11-03): in-build suite 4,342 OK / 30 expected skips,
  `ce_inputs: []`, `runtime_unverified` deliberately kept per gate;
  source ZIP `CT2Trainer-0.27-source.zip` sha256
  `264b42d6c42dac1bb434c1d0591e82ac0bec69e61e1a1c75047c6aa58126f40e`
  (14,357,294 bytes), portable ZIP
  `CT2Trainer-0.27-windows-portable.zip` sha256
  `bfcf2abc885122dfa8653fcfd0046323e7112f59c0850958688e36e014ebc135`
  (49,654,613 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `9762c8bdc2298c16bd82779f206d9a885a449261a6428187c3bd2155fc5bf1bc`,
  16,929,639 bytes, ships next to the converter).
- Lane C (2026-11-12, lane `native-lane-c-baseaddress` @ `7f81094`,
  merged into `main` as `7d92482`): roadmap class-d ratification of
  the `BaseAddress` user-symbol import (tests only; new
  `tests/test_native_baseaddress_import.py` +378 lines, 9 tests / 3
  classes). The 80 `BaseAddress` rows of the five UE5
  script-template tables (AtomicHeart v1.2, HellPie v1.0, Oregon
  v1.1, Scorn v1.0, The Callisto Protocol v1.2 - 16 per table) are
  blocked by design with the exact named class-d message while
  `BaseAddress` is undefined, and become fully supported once a
  `<UserdefinedSymbols>` `BaseAddress` entry exists - not staged
  (the UDS address is static), `dependency_ids=[]`,
  `requires=['BaseAddress']`, resolved byte-exactly through the
  engine read / write roundtrip; forged out-of-range and
  duplicate-casefold maps are refused with the named reasons. Static
  audit over the five real-table temp copies (originals
  sha256-verified unchanged): 83 as-is blocked (80 `BaseAddress` + 3
  out-of-scope) -> 3 blocked after import (all out-of-scope
  residual, original reasons intact), +16 supported per table, zero
  newly blocked, zero reason changes. Full main suite after the
  merge: 5,020 OK / 36 expected skips (baseline 5,011 + 9). Catalog
  remeasure `blocked-catalog-lane-c`: 117,809 total / 117,272
  supported / 12,974 headings / 104,123 actionable / 537 blocked -
  zero delta vs `blocked-catalog-043-tgc` (3-chunk record-level
  delta: 0 newly blocked, 0 unblocked, 0 reason changes, 0 tables
  added / removed). The 80 rows stay blocked in the shipped (as-is)
  tables by design until the user imports the symbol; a real in-game
  import + effect (AP-11) remains open by definition (this proof is
  static: no target attach, no Lua execution). Lane A (Witcher3 /
  GoW dynamic Lua symbol registration, 182 rows) in progress; Lane B
  (Octopath2 relative-address staging, 134 rows) queued after Lane A
  (compiler.py overlap).
- 0.43 the Master Trainer minimize-to-tray + window-geometry
  persistence (MT-32/MT-33) + the TGC field fix (2026-11-11,
  root-direct on `main`). MT-32: the Master Trainer can minimize
  into the system tray and restore on tray double-click -
  `master_trainer/tray.py` drives the Win32 tray icon
  (`Shell_NotifyIconW` / `RegisterClassExW` bound through
  `_bind_prototypes` with pointer-sized WPARAM/LPARAM) behind a
  bounded, named fail-closed guard: a Windows build without the
  `Shell_NotifyIconW` export (stripped user32, the Sinking City 2
  0.22.1 hotkey-bridge precedent) is the named
  `tray-platform-unavailable` refusal, a refused `RegisterClassExW`
  (Win32 87) is `tray-setup-failed`, a missing icon is
  `tray-icon-missing` - every refusal lands in the status line,
  never a crash and never a dialog; the persisted "Minimize to
  tray" preference (master-settings.json schema 9 -> 10,
  `tray_minimize`, default off) restores on start and persists on
  every change, and a persisted on preference minimizes into the
  tray at start; the tray balloon reports the trainer attach
  success / failure through the new `ui.py` `attach_observer`
  (fail-safe `_fire_attach_observer` in `poll()`), so the
  standalone trainer header and behavior stay byte-identical.
  MT-33: the Master window size / position is remembered across
  restarts - `master_trainer/window_geometry.py` pure layer (parse
  / validate / clamp), persisted in the same master-state document
  (schema 10, `window_geometry`), saved on the bounded
  `<Configure>` cadence and on close (defensive winfo guards so a
  half-destroyed window never writes a bogus rect); an invalid
  persisted geometry is the named `window-geometry-invalid`
  refusal (the default geometry) rather than a crash. TGC field
  fix: the 2026-11-11 Indiana Jones and the Great Circle (0.41)
  field log (target TheGreatCircle.exe) exposed two transient-read
  dead ends - R1 the module snapshot failed with Win32 299
  immediately after the first attach while the game was still
  loading its DLLs (299 was not in the snapshot transient retry
  set), R2 a transient 299 read during the periodic
  `_check_patches` was wrapped as a hook-receipt change ->
  PatchConflict -> engine-blocked; a failed read is not an
  observed change: F1 (`memory.py`) 299 joins the bounded snapshot
  transient retry (8 attempts, 0.05 -> 1.0 s backoff), the public
  `TRANSIENT_MEMORY_ERRORS = {299, 119, 1116, 24}` set +
  `is_transient_memory_error(exc)` classify a read failure as
  "cannot verify right now" - never "bytes changed"; F2
  (`engine.py`) a transient read in the periodic `_check_patches`
  skips that verification tick with a bounded skip streak
  (`VERIFY_SKIP_STREAK_LIMIT = 30` consecutive ticks, reset on
  every verified tick and on every confirmed (re-)attach), a
  deduped `patch-verify-skipped` debug event, and a persistent
  streak is the named fail-closed refusal; a real byte mismatch
  and a non-transient failure still block immediately (unchanged
  contract); F2b (`hooks.py`) a transient guard read in
  `_check_allocation_guards` re-raises instead of calling
  `_fail_uncertain`. +85 tests (new
  `tests/test_native_master_tray_geometry.py` (62, incl. the
  correctly session-skipped Shell_NotifyIconW smoke test) +
  `tests/test_native_tgc_field_fix.py` (17) + 6 in the
  `tests/test_native_architecture.py` /
  `tests/test_native_master_state.py` updates). Full main suite
  5,011 OK / 36 expected skips; catalog remeasure
  `blocked-catalog-043-tgc`: 117,809 total / 117,272 supported /
  12,974 headings / 104,123 actionable / 537 blocked - zero delta
  vs `blocked-catalog-042-cleanup` (3-chunk record-level delta
  audit: 0 newly blocked, 0 unblocked, 0 reason changes, 0 tables
  added / removed; 0.43 touches no plan-compile path); feature
  matrix unchanged (42/42, 7,475/7,475 over
  `w4b4-case30-20261020081722Z`); AP-11 0/6,143. VERSION 0.43 +
  CHANGELOG entry in the same change (incl. the `__version__`
  package constant sync, guarded by
  `test_version_matches_root_version_file`). The 0.43 build
  `native-20261111T184600Z-3bf9d8aa` cut from `main` @
  `0df2607` (2026-11-11): in-build suite 5,011 OK / 36
  expected skips, `ce_inputs: []`, `runtime_unverified`
  deliberately kept per gate; source ZIP
  `CT2Trainer-0.43-source.zip` sha256
  `c0011d10a5a60b78067b0cdd1a622a134088fee325ac4d544efd3ec8101438ca`
  (14,617,762 bytes), portable ZIP
  `CT2Trainer-0.43-windows-portable.zip` sha256
  `dc7a4062b56be99ea887a77ffd23e7c2c1ff38935e471d7f124ed4d775a022e9`
  (49,849,139 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `4846d7568ef4eba091261b21e678c13ab5cecbbf3468a0a57ba30d84fc7e91a4`,
  17,072,494 bytes, ships next to the converter).
- 0.42 the CE 7.5 cleanup parity + the API-export registry
  extension (2026-11-11, root-direct on `main`; the second wave
  of the CE 7.5 parity program - the two remaining bounded
  compatibility classes of the 805-row root-cause census).
  Cleanup parity: a disable-phase cleanup name that NO program
  owns is a silent no-op in CE 7.5 (`autoassembler.pas`
  L2492-2525 `unregistersymbol` appends it to the deletion list
  without an ownership check; L2625-2669 `dealloc` searches only
  this program's allocation set, read-only reference);
  CT2Trainer now drops the name from the program node and
  records it in the new program field `unowned_cleanup_dropped`
  (sorted, deduped, casefold) instead of refusing the program,
  so the record stays supported. A name live-registered by
  another supported record keeps the WP-37 handover refusal -
  the owning record releases that symbol exactly once on its
  own deactivation, so a second release from a foreign program
  is a real cross-record hazard, not a CE no-op. Because the
  first-pass entry compile runs without the table-wide
  ownership context, the drop is only provisional there: a
  plan-level re-check (after the Wave B1 loop) re-blocks a
  first-pass-supported record when one of its dropped names is
  (a) a WP-37 handover name (record-Lua
  registerSymbol/unregisterSymbol pairs or allocation-only
  programs - the owner may be the record itself) or (b) in any
  other supported record's entry-level `provides` (luaCall AOB
  symbols, ordinary AA registrations) - with the named
  single-form reason "Program may not unregister or
  deallocate the externally owned symbol X (owned by record
  N)." (the "Static AA envelope: " prefix kept for envelope
  records). API-export registry extension (RT-4.2 R7): the
  bounded Windows API export registry gains `sleep`
  (kernel32.dll) and `showwindow` (user32.dll) - the corpus
  thread idioms (HorizonForbiddenWest records `mov rcx,10 /
  call Sleep`; APlagueTaleRequiem / Resonance console-open
  threads `call ShowWindow`) now resolve with the exact
  `api_exports` marker, the same contract as the existing
  user32 entries (requires == [export], link-time resolution
  against the target's live PE export table, named fail-closed
  refusal on an absent export; a bare API name in a value
  address expression keeps the classic unsupported-provider
  refusal); the CE 7.5 tree has no GetProcAddress/kernel32 AA
  handling (it resolves via the symbol handler over target
  modules), so the bounded registry + link-time resolution is
  the clean-room equivalent. +9 tests (new
  `tests/test_native_aa_cleanup_parity.py`: the
  program-level no-op shapes incl. sorted/dedup +
  wildcard/external scoping + the label-only re2 trigger; the
  plan-level handover re-block + the unowned cascade unblock
  (the re2 12997 root shape - the provider stays supported and
  the dependent `rootsym+8` resolves with dependency_ids [1]);
  the Sleep/ShowWindow markers; the value-expression boundary)
  and 4 modules updated (`test_native_assembler`,
  `test_native_luacall_symbol_only`,
  `test_native_rt42_runtime_provider`,
  `test_native_lua_symbol_handover` - the single named
  reason), plus the deterministic MT-24 race guard in
  `test_native_master_ui` (a queue-only stub analysis worker
  for the rescan pending-marker test - the daemon thread could
  finish the one-entry table's compile before the assertion,
  making the "..." marker racy). Full main suite 4,926 OK / 35
  expected skips (4,917 from the 0.41 content + 9 new);
  catalog remeasure `blocked-catalog-042-cleanup`: 117,809
  total / 117,272 supported / 12,974 headings / 104,123
  actionable / 537 blocked (-268 vs
  `blocked-catalog-041-digit-labels` - the 3-chunk delta audit
  vs the 0.41 chunks: zero newly blocked, 268 unblocked - 26
  `Sleep` + 2 `ShowWindow` + 24 direct cleanup-ownership rows +
  216 provider cascades: the HFW `pInventoryItemResource` /
  `pAttackInfo` / `PlayerCharacter` thread cascades, the DS2
  `KeyHandlerThread` dependents, the re2 `rootsym` cascade - 12
  still-blocked rows carry the more specific named handover
  reason: DS2 `KeyHandlerThread` x10 (record 87498) + x1
  (record 87500), `pBase` x1 (record 1337263367)); feature
  matrix unchanged (42/42, 7,475/7,475 over
  `w4b4-case30-20261020081722Z`); AP-11 0/6,143. VERSION 0.42
  + CHANGELOG entry in the same change (incl. the `__version__`
  package constant sync, guarded by
  `test_version_matches_root_version_file`). The 0.42 build
  `native-20261111T044023Z-04112d15` cut from `main` @
  `377f760` (2026-11-11): in-build suite 4,926 OK / 35
  expected skips, `ce_inputs: []`, `runtime_unverified`
  deliberately kept per gate; source ZIP
  `CT2Trainer-0.42-source.zip` sha256
  `f44d248303b302b8621e80efc7c6faff476d0f27887b729546bf42c639839415`
  (14,589,013 bytes), portable ZIP
  `CT2Trainer-0.42-windows-portable.zip` sha256
  `305832ddc03487542c9a889e150b96f45c1576fa5e56819276da54b9388a5c40`
  (49,821,481 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `35389c7611715b494418b2c5bcdbd48e84f8d55a55f3deab556c4aa4d6aefd1c`,
  17,051,026 bytes, ships next to the converter).
- 0.41 the AA typed-constant package (the CE StrToQWordEx
  contract) + the digit-leading-label CE 7.5 parity fix
  (2026-11-10, root-direct on `main`; the compatibility lane
  along the reference-table-100 roadmap - the two remaining
  Death Stranding "Load Table" roots, record 130605: root #1
  the `(int)0.00` decimal-cast operand and root #2 the
  `0CurrentWeight:` digit-leading label line, whose failure
  blocked the ~243-row "no unique supported provider"
  cascade).
  Typed constants: the full typed family
  `(int|float|double|dword|qword|word|byte)` as instruction
  operand, data literal and `define` value - the integer
  family follows the CE `StrToQWordEx` contract (read-only
  reference): a `0x`/`$`-prefixed or pure-hex literal parses
  as an integer, a decimal / exponent form parses as a float
  and truncates toward zero, and an out-of-range value is the
  named refusal "Typed constant exceeds the {type}
  representation." instead of a silent wrap; the float /
  double family stays finite-only with the named `Inf` /
  `-Inf` / `NaN` spellings, and a hex literal over a float /
  double type keeps the pre-existing cast no-op. The dialect
  boundary is deliberate: a typed constant parses pure digits
  DECIMAL (the CE contract), while the unsized AA dialect
  keeps its hex-by-default reading - 41 corpus rows now
  assemble with the CE-correct bytes (byte-changing parity
  fixes, every record stays supported, incl. the Borderlands3
  `cmp [flag],(byte)2` byte-compare) and the two decimal-form
  DS `(int)0.00` rows assemble for the first time; the define
  flow needed no code change (corpus census: 164 `define(`
  calls, exactly 7 `(float)` idioms - the APlagueTale
  `define(movespeedmultiplierdefault,(float)0.64)` stays
  byte-stable as `0AD7233F`). Digit-leading labels: the CE
  7.5 label-name contract (`autoassembler.pas`
  `getPotentialLabels` L707-730 + the main path L2843-2900,
  read-only reference) - a `name:` line is a positional label
  definition iff `trystrtoint64('$'+name)` fails - implemented
  as the `_symbol_name_token()` predicate (the `_LABEL_NAME` /
  `_HEX_NAME` / `_LITERAL_TOKEN` shapes) at all eight cursor /
  symbol sites in `aa_program.py`: letter-starting names are
  byte-stable against the pre-fix behavior (incl.
  letter-leading all-hex like `ABC`); a digit-leading name is
  a program-local label only while it is not fully
  hex-parseable and not a value literal (the `0x`/`$`-hex and
  `#N`-decimal spellings the typed-constant substitution
  emits into operand streams), so `0CurrentWeight:` keeps the
  owned allocation region for the following `resb 8` padding
  while `0078:` / `11105:` keep the classic
  externally-provided symbol cursor and the `0x...` literal
  tokens never enter the program's requirements; the link
  walk's `key not in resolved` guard keeps digit-leading SCAN
  symbols (the Octopath1 `8PathBattleResult` / `8PathSteal`
  aobscanmodule pairs) on the classic resolution path
  (corpus census: 267 distinct digit-leading label names,
  262 all-hex unchanged, 5 non-hex: the DS trio + the
  Octopath pair, both regression-guarded). +38 tests (new
  `tests/test_native_aa_typed_constants.py` 23 + new
  `tests/test_native_aa_digit_labels.py` 15 with the NASM
  byte pins: the digit-vs-letter byte-stable blocks, the DS
  root idiom `C780BC02000000000000` + 24 reservation zero
  bytes, the duplicate digit-label refusal with letter
  parity, the inlined Octopath aobscanmodule replica); full
  main suite 4,917 OK / 35 expected skips (4,879 from the
  0.40 content + 38 new); catalog remeasure
  `blocked-catalog-041-digit-labels`: 117,809 total /
  117,004 supported / 12,974 headings / 103,855 actionable /
  805 blocked (-248 vs `blocked-catalog-040-process-id` -
  the 3-chunk delta audit vs the 0.40 chunks: zero newly
  blocked, 248 unblocked (the DS pair 122+121=243 rows, root
  record 130605 + the "no unique supported provider" cascade:
  PlayerStats, PlayerBattery, CurrentWeight, ...) plus 5 x
  `dq (double)Inf` records (AtomicHeart / HellPie / Oregon /
  Scorn / Callisto), zero reason changes); feature matrix
  unchanged (42/42, 7,475/7,475 over
  `w4b4-case30-20261020081722Z`); AP-11 0/6,143. VERSION 0.41
  + CHANGELOG entry in the same change (incl. the
  `__version__` package constant sync, guarded by
  `test_version_matches_root_version_file`). The 0.41 build
  `native-20261110T210856Z-5811040c` cut from `main` @
  `c724a7e` (2026-11-10): in-build suite 4,917 OK / 35
  expected skips, `ce_inputs: []`, `runtime_unverified`
  deliberately kept per gate; source ZIP
  `CT2Trainer-0.41-source.zip` sha256
  `05ef6cabca08adcca8a084722581b7d553966e480e28274a4a72f4b31b9c1964`
  (14,580,191 bytes), portable ZIP
  `CT2Trainer-0.41-windows-portable.zip` sha256
  `533bee676d0ed5c487741cb4919af8f4370f2bee1c5c26181ed5f3f0c3753a77`
  (49,814,303 bytes; the frozen `CT2Trainer-Master.exe`
  sha256 `ce07c42cf22c57eeeffa08be74ff562d3a7dcfca5f4c2d14121c784acd24c6f`,
  17,049,435 bytes, ships next to the converter). The
  DeathStrandingDC Update31 pair (243 rows) is now fully
  supported - the last blocked cascade of the 0.40 catalog
  outside the documented createThread / cleanup-ownership /
  runtime-provider rows; Octopath stays at 0 blocked; the
  live-target runtime confirmation stays in the RT-6 / field
  lane (`runtime_unverified` kept per gate).
- 0.40 the Master Trainer process identification in picker +
  details (MT-31) + the bounded zero-transfer transient-write
  retry in `memory.py` (2026-11-10, root-direct on `main`; the
  adopted 0.40 candidates from the online evaluation - the
  Cheat Engine forum "Open Process By PID" thread: the
  multi-instance indistinguishability problem (several running
  instances of the same game name with no way to tell them
  apart); the WeMod UI threads and the Game Cheats Manager
  front-end survey: layout / visibility / trainer-options
  remain covered by the 0.36 multi-column grid and the 0.37
  per-table process binding, tags / search / filters /
  last-used -> covered by MT-13/15/18/27, auto-update / online
  catalog / game launch -> out of scope for the private
  own-use model (no install-path data in the read-only table
  model) - plus the reliability lane completing the 0.39
  read-side symmetry, the read / write transient pair).
  MT-31: the use case's "choose which table runs against which
  process" direction - MT-10/11/28 persist the attach mode and
  the process binding, but the picker and the table-details
  "Running now" row could not TELL the candidates apart. The
  `ProcessSnapshotEntry` gains the optional identification
  fields `path` (the full image path), `creation_time` (the
  process start, Unix epoch seconds) and `pointer_size` (4 /
  8, the target bitness), all default `None` (refused /
  unavailable - fail-closed: the row keeps the byte-stable
  name + PID form, the `pid` / `name` decision fields are
  never touched); the snapshot listers stay cheap (name + PID
  only, the 30 s auto-rescan tick keeps its contract); the
  bounded per-candidate enrichment runs only where the user
  asks for it - the process picker rows and the table-details
  "Running now" row, never per poll tick: `enrich_candidates`
  applies the platform `default_process_enricher` (the
  injectable test seam) to each entry of the bounded candidate
  set, every per-entry failure fails closed (the entry stays
  unenriched, a non-entry result is refused as well); the
  Windows backend opens the process with
  `OpenProcess(PROCESS_QUERY_INFORMATION)` only - no other
  rights - and asks `QueryFullProcessImageNameW` /
  `GetProcessTimes` (FILETIME ticks -> Unix seconds via the
  11644473600 s epoch delta) / `IsWow64Process2` (I386 -> 4,
  AMD64 -> 8, anything else unknown), the handle closed in a
  finally, a refused handle / query / missing export keeps
  the entry unenriched, no error propagates; the
  Linux/SteamOS backend takes the `/proc/<pid>/exe` link
  target (under Proton the compatibility-prefix path of the
  bound Windows EXE) and the `starttime` field 22 of
  `/proc/<pid>/stat` plus the system `btime` at `SC_CLK_TCK`
  (the bitness is not provable from `/proc` and stays `None`;
  any read failure keeps the entry unenriched); the picker
  rows render through `candidate_display_text` - name + PID
  always (byte-stable against the pre-0.40 row format while
  unenriched), the proved facts appended (path / "started
  YYYY-MM-DD HH:MM" via `format_creation_time` / "64-bit" /
  "32-bit"), a refused fact never renders; the table-details
  "Running now" row renders each running bound candidate with
  its identification facts (the bare name + PID row while
  refused); the waiting-view "Running now" line keeps its
  cheap name + PID form (never enriched). Zero load-path
  effect - the MT-9 gate re-checks the table independently at
  load time; the attach decision (the PID pin) is unaffected
  by the enrichment. Reliability lane: the write-side
  symmetry of the 0.39 transient-read retry - a
  `WriteProcessMemory` call that FAILED with the field-observed
  transient set {299, ERROR_MORE_DATA=119,
  ERROR_BAD_LENGTH=1116, ERROR_INVALID_ID=24} and transferred
  NOTHING is now retried in `memory._write_checked` with the
  bounded exponential backoff (exactly 4 attempts, backoff
  0.05 -> 0.25 s, the sleep under the caller's lock, the
  snapshot-retry / read-retry precedent); a partial transfer
  (a call that moved any bytes, failed or not) or any
  non-transient code is NEVER retried and lands in the
  existing uncertain-write protocol unchanged (fail-closed -
  the "never silently retries a PARTIAL write" contract holds;
  after the budget the original error surfaces as before).
  +46 tests (`tests/test_native_master_ui_mt31.py` 12 +
  `tests/test_native_memory_write_retry.py` 7 + the MT-31
  additions in `tests/test_native_master_process_watch.py`
  +23 and `tests/test_native_master_process_picker.py` +4;
  baseline pinning in the MT-12 / MT-22 / MT-28 UI tests);
  full main suite 4,879 OK / 35 expected skips (4,833 from
  the 0.39 content + 46 new; the 5 SYMLINKS_OK-guarded procfs
  enrichment tests are expected skips where the symlink seam
  is unavailable); catalog zero delta
  `blocked-catalog-040-process-id` (the 3-chunk audit
  byte-identical vs `blocked-catalog-039-autoload`,
  2026-11-10): 117,809 total / 116,756 supported / 60,161
  staged / 103,607 actionable / 12,974 headings / 1,053
  blocked - **zero delta** (zero newly blocked, zero reason
  changes); feature matrix unchanged (42/42, 7,475/7,475 over
  `w4b4-case30-20261020081722Z`); AP-11 0/6,143. VERSION 0.40
  + CHANGELOG entry in the same change (incl. the
  `__version__` package constant sync, guarded by
  `test_version_matches_root_version_file`). The 0.40 build
  `native-20261110T093203Z-82c49872` cut from `main` @
  `e611e9e` (2026-11-10): in-build suite 4,879 OK / 35
  expected skips, `ce_inputs: []`, `runtime_unverified`
  deliberately kept per gate; source ZIP
  `CT2Trainer-0.40-source.zip` sha256
  `46ad5dd9f9adc872e320dd4aec2362e007020ae879bba0cc8fe0621e44c34c40`
  (14,569,029 bytes), portable ZIP
  `CT2Trainer-0.40-windows-portable.zip` sha256
  `5075586c7b0f3251749c8e3e60ec0db7fea251db39190b59b63273a4e9b10bd6`
  (49,809,535 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `52f6da1cebfc44a0dc791d4b5758112342b5a1d42c9fc9656901a16d1a5eb03f`,
  17,048,910 bytes, ships next to the converter). The read /
  write transient pair is now complete (read: 0.39,
  `memory._read_exact`; write: 0.40, `memory._write_checked`);
  the live-target runtime confirmation stays in the RT-6 /
  field lane (`runtime_unverified` kept per gate).
- 0.39 the Master Trainer per-table auto-load policy (MT-29) + state
  folder / debug log quick access (MT-30) + the bounded transient-read
  retry in `memory.py` (2026-11-10, root-direct on `main`; the adopted
  0.39 candidates from the online evaluation - the WeMod community
  thread re-read: the layout / visibility / trainer-options requests
  remain covered by the 0.36 multi-column grid and the 0.37 per-table
  process binding - plus the reliability lane closing the documented
  open issue of the 0.38 ledger). MT-29: the per-table auto-load
  policy (`table-autoload.json` schema 1, under the state home, keyed
  by the table content sha256 - the same identity as the MT-24/27/28
  sidecars, so a policy survives a rename and follows a
  content-identical file to another root); only the non-default policy
  persists - one `manual-only` entry per table, the absence of an
  entry is the documented automatic default; a manual-only table is
  never auto-loaded (no auto-load request and no picker - the
  waiting line shows the stable named detail "auto-load suppressed
  (all N bound table(s) for this process are manual-only; load one
  explicitly)" instead, and an open choice is dropped back to
  waiting), while every explicit load path (double-click / Enter,
  "Load this table", the "Load table" picker, `Recent:`) keeps
  working unchanged; the policy set is a zero-arg callable
  re-evaluated on every orchestrator tick (a policy change applies
  from the next tick); the row context menu offers the toggle
  ("Auto-load: manual only" / "Auto-load: automatic" - the label
  names the action, the pin-toggle convention; immediate persist +
  status line; the disabled "Auto-load policy (no content sha)" item
  for a table without a content sha), the MT-22 table-details window
  gains the "Auto-load policy" row, and the waiting-view filter
  matches the persisted policy text. MT-30: the waiting view gains
  two master-only header buttons - "State folder..." and
  "Debug log..." (the standalone trainer header stays
  byte-identical) - opening the persisted state home (the
  master-state document, the table index, the per-table sidecars,
  and the `forced-recovery/` archives created by the 0.38 `--force`
  forced start) and the trainer debug log at its exact
  `debug_log.default_log_path()` in the platform file manager /
  default handler (the pure `state_access.py` layer: the named
  `StateAccessRefusal` codes `state-folder-bad` /
  `state-folder-missing` / `debug-log-bad` / `debug-log-missing` /
  `no-opener` / `bad-path` / `opener-failed`; every refusal lands in
  the status line - never a dialog, never a crash). Reliability lane:
  the field-observed transient "ReadProcessMemory failed (Win32
  error 299)" (0.22 / 0.30 / 0.31 field logs, Proton - no public
  Windows constant is named for 299, so it is documented as a
  field-observed transient code) is now retried in
  `memory._read_exact` with the bounded exponential backoff - the
  transient set {299, ERROR_MORE_DATA=119, ERROR_BAD_LENGTH=1116,
  ERROR_INVALID_ID=24} (the same codes the module-snapshot retry
  treats as transient), exactly 4 attempts, backoff 0.05 -> 0.25 s
  (the sleep under the caller's lock, the snapshot-retry precedent);
  a partial result (a successful call that transferred fewer bytes)
  is NOT retried - an unexpected state, not a transient error code;
  after the budget the original error is raised unchanged
  (fail-closed, no silent success). +73 tests
  (`tests/test_native_master_autoload.py` 33 +
  `tests/test_native_master_ui_mt29.py` 14 +
  `tests/test_native_master_ui_mt30.py` 20 +
  `tests/test_native_memory_read_retry.py` 6) + the 7 baseline
  updates (3 in `tests/test_native_master_notes.py`, 2 in
  `tests/test_native_master_ui_mt22.py`, 2 in
  `tests/test_native_master_ui_mt24.py` - the details-window and
  waiting-view assertions gain the new rows); full main suite 4,833
  OK / 30 expected skips (4,760 from the 0.38 content + 73 new);
  catalog zero delta `blocked-catalog-039-autoload` (the 3-chunk
  audit byte-identical vs `blocked-catalog-038-force`,
  2026-11-10): 117,809 total / 116,756 supported / 60,161 staged /
  103,607 actionable / 12,974 headings / 1,053 blocked - **zero
  delta** (zero newly blocked, zero reason changes); feature matrix
  unchanged (42/42, 7,475/7,475 over
  `w4b4-case30-20261020081722Z`); AP-11 0/6,143. VERSION 0.39 +
  CHANGELOG entry in the same change (incl. the `__version__` package
  constant sync, guarded by
  `test_version_matches_root_version_file`). The 0.39 build
  `native-20261110T051241Z-57bf7d47` cut from `main` @ `17a22f7`
  (2026-11-10): in-build suite 4,833 OK / 30 expected skips,
  `ce_inputs: []`, `runtime_unverified` deliberately kept per gate;
  source ZIP `CT2Trainer-0.39-source.zip` sha256
  `14163e7475477c177be339d06fd5ba7b9a7016667405669b084faed25035a923`
  (14,549,960 bytes), portable ZIP
  `CT2Trainer-0.39-windows-portable.zip` sha256
  `7d5d7903f1be5df0eac0f1067d5c2ca596321a41ea37381e033e5deb175ec8b6`
  (49,800,752 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `e0db5b2e2f41ec816089486ca57a2c0b1424523e7ee8450335053923ab629e47`,
  17,042,819 bytes, ships next to the converter). The documented
  open issue of the 0.38 ledger (the Win32 error 299 transient read
  failure, `memory._read_exact` without a bounded retry) is closed
  by this release; the live-target runtime confirmation stays in
  the RT-6 / field lane (`runtime_unverified` kept per gate).
- 0.38 the --force forced start for the documented SteamOS state-lock
  dead end (2026-11-09, root-direct on `main`; user request 2026-11-09 -
  the recurring SteamOS problem that the trainer does not start at all
  because of the state lock; diagnosis: the user's Indiana Jones and the
  Great Circle Proton field logs (the 0.22 / 0.30 / 0.31
  `.ct2debug.log` files) showed an interrupted recovery transaction left
  `recovery.lock` behind, the recovery-eligibility assessment stopped
  classifying the state, and the conservative refusal "A recovery
  transaction owns this state" fired on every start - on SteamOS the user
  cannot easily delete the state folder). The `--force` startup parameter
  (accepted by the frozen trainer EXE (`launcher.py`), the source CLI
  `run` + `master` commands (`__main__.py`) and the frozen
  `CT2Trainer-Master.exe` (`tools/native_master.py`)) skips the
  state-lock safety prompts: a recoverable stale state
  (`StaleStateRecoverable`, the state-lock owner proven dead) or
  unfinished receipts (`StaleArtifactsRecoverable`) is archived through
  the tested `perform_stale_recovery` path without the confirmation
  dialog; the fence dead end (the plain `StateError` "A recovery
  transaction owns this state", incl. the "state.lock already exists"
  probe fallback) triggers the new bounded forced reclaim in the pure
  `state_force.py` layer (`force_reclaim`): every recorded trainer-side
  owner (the state lock, the recovery fence, the session record, the
  matching shared process claims under `_process_sessions`) is probed
  with the tested process probe (one observation, one retry on a
  transient "unknown"); a proven-alive trainer-side owner is still
  refused with its named reason - the one hard data-safety boundary that
  stays even under `--force` (the `LiveStateConflict` path now refuses
  without the termination prompt); every other case (proven-dead owner,
  unprovable owner: transient probe failure, legacy lock without a
  creation identity, unparseable document) quarantines the blocking
  artifacts (`state.lock`, `recovery.lock`, `session.json`,
  `state.json.tmp`, `oneshot.json.tmp`, the hook receipts / global-pool,
  this trainer's shared claims) into a timestamped
  `forced-recovery/<UTC stamp>-<trainer id>/` archive next to the state
  folder, with the evidence document `force-reclaim.json`
  (`ct2trainer-forced-reclaim/v1`: owner observations, moved files with
  size + sha256, the preserved `state.json`); the saved `state.json`
  (the user's saved wishes) is always preserved, so the saved toggles
  survive the forced reclaim; the engine default state directories are
  factored out as `default_state_dirs` (single fact shared by the engine
  claim and the reclaim path); the master wiring is
  `run_master(..., force=)` -> `MasterApp.force` -> the `_start_load`
  loop (auto recovery without prompt, forced reclaim via
  `default_state_dirs(plan, app.state_dir_for(plan))`, live-conflict
  refusal, the `except StateError` clause before the generic
  `except Exception`; the status line + fail-closed loop guard
  unchanged); debug-log events `state-force-recovered` /
  `state-force-reclaimed` / `state-force-refused` /
  `state-force-failed`. On Steam / SteamOS: `--force` in the game's
  launch options (Properties -> Launch Options) so the Proton-wrapped
  trainer starts without any dialog. +27 tests
  (`tests/test_native_state_force.py` 13 - the pure `force_reclaim`
  layer: the proven-alive state-lock owner refusal (state untouched),
  the dead-owners quarantine with the saved-state preservation, the
  dead fence owner reclaim, the own shared claim moved + the foreign
  claim kept, the live shared-claim owner refusal, the no-artifacts
  no-op, the unprovable-owner quarantine with evidence, the non-Windows
  no-probe refusal, the corrupt lock quarantine, the hooks /
  global-pool reclaim, the legacy lock quarantine, the
  moved-bytes-preserved-with-sha proof, the archive-collision refusal;
  `tests/test_native_master_force.py` 8 - the master Tk wiring: the
  forced stale-state / stale-artifacts auto recovery without prompt, the
  stale-recovery failure fail-closed start refusal, the fence dead-end
  reclaim + start, the reclaim refusal fail-closed, the live-conflict
  refusal without prompt, the custom state dir addressed by the
  reclaim, the non-force app still prompts;
  `tests/test_native_ui_recovery_flow.py` +6 `RunTrainerForceFlowTests`
  - the `run_trainer(force=)` branches: the forced stale-state /
  stale-artifacts auto recovery without prompt, the stale-recovery
  failure exit, the fence dead-end reclaim + start, the reclaim refusal
  exit, the live-conflict refusal without the termination prompt); full
  main suite 4,760 OK / 30 expected skips (4,733 from the 0.37 content +
  27 new); catalog remeasure `blocked-catalog-038-force` (3-chunk
  deep-equal audit over the 151 reference tables, 2026-11-09): 151/151
  loaded, 0 load errors, 117,809 total / 116,756 supported / 60,161
  staged / 103,607 actionable / 12,974 headings / 1,053 blocked -
  **zero delta** vs `blocked-catalog-037-attach` (per-table
  count/reason/sha changes: 0); feature matrix unchanged (42/42,
  7,475/7,475 over `w4b4-case30-20261020081722Z`); AP-11 0/6,143.
  VERSION 0.38 + CHANGELOG entry in the same change. The 0.38 build
  `native-20261109T211151Z-03e89050` cut from `main` @ `da1e68f`
  (2026-11-09): in-build suite 4,760 OK / 30 expected skips,
  `ce_inputs: []`, `runtime_unverified` deliberately kept per gate;
  source ZIP `CT2Trainer-0.38-source.zip` sha256
  `e2b466adc7abfb191bbd2b50f8304739a1e82cbf487099d4ecd6fd77cc3f3d0c`
  (14,521,497 bytes), portable ZIP
  `CT2Trainer-0.38-windows-portable.zip` sha256
  `df5ccfa373c8f5deb6be85f36e75941a1c0b3a9f13afae23c03f1644f9290fc4`
  (49,781,948 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `5d2cc5544eb6a29f1c3283f05e809e392d0038a1f59456c9d52f0356e519231d`,
  17,026,316 bytes, ships next to the converter). Documented open
  issue (not part of 0.38): the Win32 error 299 transient read failure
  during a live `PatchConflict` receipt verification on Proton
  (`memory._read_exact` has no bounded retry) remains the upstream
  trigger of the stale state on Deck - `--force` recovers from it; the
  bounded retry stays a separate reliability lane.
- 0.37 Master Trainer per-table process binding persistence (MT-28)
  (2026-11-09, root-direct on `main`; online-evaluated in
  `master_trainer/ROADMAP.md`, the "0.37 per-table process binding"
  section - a re-read of the WeMod community thread "UI
  customization" (community.wemod.com/t/ui-customization/371434) -
  the thread's layout / visibility requests remain covered by the
  0.36 multi-column grid - plus a code audit of the Master Trainer
  attach flow that found the gap against the use case's core
  requirement ("choose which table runs and which process it
  attaches to - remember the configuration"): MT-11 persists the
  attach mode, and the picker's chosen PID is "pinned for the
  session" only, so a restart loses the per-table process choice).
  MT-28: the user's explicit process choice (every picker origin:
  auto-load, explicit load, table choice, re-attach after a
  detach) is remembered per table against the table content
  sha256 (the same identity as the MT-24 analysis and the MT-27
  notes documents, so a remembered choice survives a rename and
  follows a content-identical file to another root). The persisted
  document is `table-attach.json` (schema 1, under the state home;
  strict key-set / field validation - an unknown field is a named
  `AttachRefusal`, never a silent drop; checksummed
  canonical-JSON envelope; `ATTACH_ENTRIES_LIMIT` = 1024 entries,
  `evict_oldest` by `updated_at`, ties by sha256; a refused
  document is treated as absent, documented, never a silent
  reset). The pure layer lives in `table_attach.py`
  (`binding_entry`, `AttachStore`, `binding_target` - honour the
  stored PID only while it is one of the live candidates whose
  name still matches the bound process - case-insensitive;
  `details_attach_lines` - the MT-22 details-window "Remembered
  process" row). `master_ui.py`: `MasterApp.attach_store`; the
  process picker gains `preselect_pid`; `_binding_candidate` (the
  persisted binding for a table's content sha, or None - a table
  without a content sha cannot carry a binding, the documented
  MT-27 identity rule); the binding is consulted in `_auto_load`
  (a live binding outranks the documented smallest-PID rule in
  `auto` mode; preselected in the picker in `ask` mode - the
  picker still opens, the documented contract),
  `_load_selected_table`, `_picker_chosen` (the table-choice path)
  and `_detach_or_attach` (the `attach` origin addresses the
  loaded table through the sidecar sha); `_remember_attach_choice`
  persists the explicit choice before the picker state is torn
  down (a refused choice is not persisted, no status-line noise on
  the hot pick path). Zero load-path effect - the MT-9 gate
  re-checks the table independently at load time. Remaining
  candidates (updated): the game launch integration (needs
  install-path data; out of scope for the read-only table model).
  +68 tests (`tests/test_native_master_attach.py` 53 - the pure
  layer: the schema-1 document round-trip, the strict key-set /
  field validation refusals, the checksummed envelope, the entry
  shape validation, `evict_oldest` order, `AttachStore`
  set / get / has / clear, refused documents treated as absent,
  `binding_target` (live + name match, stale, foreign),
  `details_attach_lines`; `tests/test_native_master_ui_mt28.py`
  15 - the Tk wiring: the `MasterApp.attach_store` sidecar, the
  picker preselect in `ask` mode (with / without / stale binding),
  the persistence of the explicit choice from every origin, the
  `auto`-mode honouring (live binding outranks the smallest-PID
  rule; stale / missing binding keeps the pre-0.37 behavior), the
  no-content-sha guard, the MT-22 details-window row) + the
  baseline details-line assertion updates in
  `tests/test_native_master_ui_mt22.py` (2),
  `tests/test_native_master_notes.py` (2) and
  `tests/test_native_master_ui_mt24.py` (2); full main suite 4,733
  OK / 30 expected skips (4,665 from the 0.36 content + 68 new);
  catalog remeasure `blocked-catalog-037-attach` (3-chunk
  deep-equal audit over the 151 reference tables, 2026-11-09):
  151/151 loaded, 0 load errors, 117,809 total / 116,756 supported
  / 60,161 staged / 103,607 actionable / 12,974 headings / 1,053
  blocked - **zero delta** vs `blocked-catalog-036-grid`
  (per-table count/reason/sha changes: 0); feature matrix
  unchanged (42/42, 7,475/7,475 over
  `w4b4-case30-20261020081722Z`); AP-11 0/6,143. VERSION 0.37 +
  CHANGELOG entry in the same change. The 0.37 build
  `native-20261109T154005Z-4ad8e339` cut from `main` @ `27dbf0d`
  (2026-11-09): in-build suite 4,733 OK / 30 expected skips,
  `ce_inputs: []`, `runtime_unverified` deliberately kept per gate;
  source ZIP `CT2Trainer-0.37-source.zip` sha256
  `a49bdd7d738de9551a1d971430ed9f7b0a212ec0d4a2afd8667e1f87ec61d301`
  (14,506,715 bytes), portable ZIP
  `CT2Trainer-0.37-windows-portable.zip` sha256
  `5cdb23b24c0757cb047ddd72ae673614fc6bccee960747079849fe325785c3ce`
  (49,762,223 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `c2a1a6948fa28248d36a6defa5a116867620261e55bdcfe1e144cd301060a9de`,
  17,017,090 bytes, ships next to the converter).
- 0.36 Master Trainer multi-column trainer grid (MT-21)
  (2026-11-09, root-direct on `main`; online-evaluated in
  `master_trainer/ROADMAP.md`, the "0.36 multi-column trainer grid"
  section - WeMod's cheat list layout: the official WeMod community
  thread "UI customization"
  (community.wemod.com/t/ui-customization/371434, 2025-09-11)
  records the staff-confirmed behavior - "The cheat list collapses
  to a single column under a certain size so nothing is hidden.
  There are also minimum width constraints to prevent it from ever
  being hidden" - a multi-column cheat list with the clamped
  single-column collapse and a per-column width floor, the exact
  multi-screen / multi-monitor use case the thread is about; the
  2025-09-22 follow-up in the same thread (trainer options "highly
  compacted ... unreadable" on a portrait / narrow display)
  corroborates the width-floor requirement).
  MT-21: the trainer row grid can run in up to three side-by-side
  columns. The requested column count (1 / 2 / 3, default 1)
  persists in the master state (master-settings.json schema 8 -> 9,
  `grid_columns`; strict int validation in 1..3; a schema-8
  document carrying the field is refused as an unknown field;
  schema-1..8 documents promote with the documented default 1) and
  is handed to the trainer window on table load. The trainer header
  gains the **"Columns: N"** cycle button (master only - the
  standalone trainer header stays byte-identical and always renders
  the single column): 1 -> 2 -> 3 -> 1, immediate re-render, the
  requested count persisted through the callback on every change.
  The pure grid layer lives in `ui_rows.py`: `build_grid`
  (per-column row lists; `columns == 1` byte-stable against
  `build_rows`; otherwise the reference rows are emitted at the
  full width, split into top-level units (`row_units` - a section
  with its children never splits across columns; an indented row
  without a top-level unit is a named refusal), the
  width-independent unit heights flow shortest-column-first
  (`flow_units`, ties to the lower column index) and each column is
  re-emitted at its own width with the column x0 baked into every
  row rectangle (`column_layout` - equal widths, the leftover
  pixels to the leftmost columns; the columns always fill the width
  exactly)); `effective_columns` clamps the requested count to what
  fits (two columns need 652 px, three need 984 px; a column never
  falls below the 320 px floor). `ui.py`:
  `TrainerWindow(..., columns=1, on_columns_changed=None)` with
  named kwarg validation; per-column pagination and per-column
  hit-testing (x picks the column, y the row inside that column
  with its own page offset); the right-anchored renderer positions
  derive from the baked `row.hit` rectangles. `master_ui.py`: the
  app loads / persists the preference and the handoff carries
  `columns` + the cycle callback (the named app-level refusal is
  swallowed by the window handler - the window can only produce 1 /
  2 / 3 by construction). The standalone trainer is untouched
  beyond the new default-valued constructor arguments. Zero
  load-path effect - the MT-9 gate re-checks the table
  independently at load time. Remaining candidates (updated): the
  game launch integration (needs install-path data; out of scope
  for the read-only table model). +55 tests
  (`tests/test_native_ui_grid.py` 37 - the pure grid layer:
  effective_columns thresholds, column_layout incl. the leftover
  distribution + the exact-fit cases + the width-fill invariant,
  row_units (split at indent 0, coverage, the orphan refusal),
  flow_units determinism (shortest-column-first, ties, the
  section-unit integrity), build_grid byte-stability vs build_rows
  / every-row-exactly-once / section integrity / deterministic flow
  / column geometry / x0 baking / expanded value / value text /
  search / no-match / hidden-children / height constants / kwarg
  refusals; `tests/test_native_master_ui_mt21.py` 14 - the app
  default on a fresh state home, the persisted restore, the
  immediate persistence, the named app-level refusals (0 / 4 / '2'
  / True / None / [2], state + document untouched), the schema-8
  document promotion via a hand-written checksum-bound document,
  the handoff columns + callback, the window handler persistence,
  the handler refusal swallow, the columns kwarg default +
  validation, the header button present only when wired
  (standalone byte-identical), the cycle label + notify 1 -> 2 ->
  3 -> 1, the 2-column render + per-column hit test (incl. the
  column gap), the narrow-window clamp 700 -> 2 / 320 -> 1, the
  standalone always-one-column invariant; the grid tests in
  `tests/test_native_master_state.py` 4 - the schema-9 document
  round-trip, the grid_columns validation, the schema-8 promotion,
  the schema-8-with-field refusal) + the baseline handoff
  assertion updates in `tests/test_native_master_ui.py` (4); full
  main suite 4,665 OK / 30 expected skips (4,610 from the 0.35
  content + 55 new); catalog remeasure
  `blocked-catalog-036-grid` (3-chunk deep-equal audit over the 151
  reference tables, 2026-11-09): 151/151 loaded, 0 load errors,
  117,809 total / 116,756 supported / 60,161 staged / 103,607
  actionable / 12,974 headings / 1,053 blocked - **zero delta** vs
  `blocked-catalog-035-notes` (per-table count/reason/sha changes:
  0); feature matrix unchanged (42/42, 7,475/7,475 over
  `w4b4-case30-20261020081722Z`); AP-11 0/6,143. VERSION 0.36 +
  CHANGELOG entry in the same change. The 0.36 build
  `native-20261109T114726Z-15c3d9ab` cut from `main` @ `d071884`
  (2026-11-09): in-build suite 4,665 OK / 30 expected skips,
  `ce_inputs: []`, `runtime_unverified` deliberately kept per gate;
  source ZIP `CT2Trainer-0.36-source.zip` sha256
  `79464f02cd71492763656ca0ff3283a240c3579b9f52df3bcc18857dabb3d1be`
  (14,490,858 bytes), portable ZIP
  `CT2Trainer-0.36-windows-portable.zip` sha256
  `089fc92b0c5758ba758fdc88bb92e11d8e3b3e36c28d04231f27b3eeaecceac0`
  (49,751,886 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `07ebef319b55d686c4f76cdb6f07440a2b4934fc8943f9f72b402d62c4c49fe8`,
  17,006,463 bytes, ships next to the converter).
- 0.35 Master Trainer per-table notes / tags (MT-27)
  (2026-11-09, root-direct on `main`; online-evaluated in
  `master_trainer/ROADMAP.md`, the "0.35 per-table notes / tags"
  section - the trainer / table manager library-organization
  patterns: game-trainer-manager (Karasukaigan) organizing + local
  real-time fuzzy search + Pin to Top (already MT-13/18) + CSV data
  storage, Fling-Trainer-Manager (OscarZhang-735) local catalog with
  search across main + archive catalogs, FLiNG per-trainer metadata
  (option counts, game version, last updated - already covered by
  the MT-24 Entries / Blocked columns and the Size / Modified /
  Last-used columns), WeMod library organization patterns).
  MT-27: the waiting view gains the **Note column** (last, width
  160) - the persisted per-table organization metadata: the note
  text truncated to one line (an ellipsis marks a cut,
  `NOTE_COLUMN_MAX` = 60 characters) plus the tags in brackets
  (`note [tag-a, tag-b]`); note-only and tag-only entries both
  render; empty while no note exists. The row context menu offers
  **"Edit note..."** between "Load this table" and the pin toggle -
  a small Toplevel with the note (multi-line text, bounded at
  `NOTE_MAX_LEN` = 500 characters) and a comma-separated tag entry
  (bounded at `TAGS_LIMIT` = 8 tags x `TAG_MAX_LEN` = 40
  characters, stripped, casefold-deduped first-spelling-wins); a
  named refusal at save time (note over the limit, a tag too long,
  too many tags) is shown in the dialog's own label - the dialog
  stays open, the persisted document is untouched; a table without
  a content sha (unreadable / never scanned) is refused in the
  status line, no dialog opens; single window, lift on second open,
  closed on trainer entry with the rest of the waiting view.
  Persistence: `table-notes.json` (schema 1, under the state home)
  - **keyed by the table content sha256** (the same identity as the
  MT-24 analysis document), so a note survives a rename within a
  root and follows a content-identical file to another root; one
  entry per noted table (`{"note", "tags", "updated_at"}`); strict
  key-set / field validation of the master-state discipline (an
  unknown field is a named refusal, never a silent drop);
  checksummed canonical-JSON envelope; `NOTES_ENTRIES_LIMIT` = 1024
  entries, `evict_oldest` by `updated_at` (ties by sha256 -
  deterministic); a refused document is treated as absent
  (documented, never a silent reset). No master-state schema bump
  (the MT-24 sidecar precedent - the notes live in their own
  checksum-bound document). Search + details: the waiting-view
  filter now also matches the note text and every tag (the pure
  `filter_tables` gains the optional `note_lookup`, keyed by the
  table content sha; a table matches when ANY of them matches;
  `note_lookup=None` is the exact pre-0.35 behavior); the MT-22
  table-details window gains the note / tag rows after the
  entry-analysis block (`none` while the table carries no
  organization metadata). No index mutation, no table-file access,
  zero load-path effect - the MT-9 gate re-checks the table
  independently at load time. Remaining candidates (evaluated, not
  yet adopted): the MT-21 multi-column trainer grid; the game
  launch integration (needs install-path data). +67 tests
  (`tests/test_native_master_notes.py`: the pure layer -
  `parse_tags` rules, the `note_entry` builder, the schema-1
  document discipline (unknown fields, checksum, schema, key,
  timestamp, entry-limit), `evict_oldest` determinism,
  `NotesStore` (set / clear / eviction /
  refused-document-as-absent), the column / details text helpers,
  the filter extension - plus the Tk wiring: the Note column (11
  row values), the menu order (`Table details` / `Load this table`
  / `Edit note...` / `Pin to top`), the editor (prefill, save
  persistence + re-render, cancel, the over-limit note / over-
  long tag refusal inside the dialog, the no-content-sha and the
  missing-entry refusal in the status line, the second-open
  lift), the details-window note / tag rows); full main suite
  4,610 OK / 30 expected skips (4,543 from the 0.34 content + 67
  new); catalog remeasure `blocked-catalog-035-notes` (3-chunk
  deep-equal audit over the 151 reference tables, 2026-11-09):
  151/151 loaded, 0 load errors, 117,809 total / 116,756 supported
  / 60,161 staged / 103,607 actionable / 12,974 headings / 1,053
  blocked - **zero delta** vs `blocked-catalog-034-mt26`
  (per-table count/reason/sha changes: 0); feature matrix
  unchanged (42/42, 7,475/7,475 over
  `w4b4-case30-20261020081722Z`); AP-11 0/6,143. VERSION 0.35 +
  CHANGELOG entry in the same change. The 0.35 build
  `native-20261109T054146Z-c5f18494` cut from `main` @ `65d8fbe`
  (2026-11-09): in-build suite 4,610 OK / 30 expected skips,
  `ce_inputs: []`, `runtime_unverified` deliberately kept per gate;
  source ZIP `CT2Trainer-0.35-source.zip` sha256
  `575ee8ad6f0864bd8ff39f3ae547bb629d5c128938cff792e9c4fb7362fbcdac`
  (14,474,384 bytes), portable ZIP
  `CT2Trainer-0.35-windows-portable.zip` sha256
  `488d7453ca0433f843c1e46a2241142347aa2ee41390ed334d6068ed30e42d34`
  (49,737,899 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `0c53908c267746cabd74e1ef091daa35d31eb94c4d0accc6401085d7e8c59ccc`,
  16,999,124 bytes, ships next to the converter).
- 0.34 Master Trainer multi-root table index (MT-26)
  (2026-11-09, root-direct on `main`; online-evaluated in
  `master_trainer/ROADMAP.md`, the "0.34 multi-root table index"
  section - the Cheat Engine Table Manager (2026) feature set, whose
  core capability is the multi-folder table index, the
  trainer-manager import / organize / search / pin patterns
  (game-trainer-manager (Karasukaigan), Cheat Happens Trainer
  Manager), the WeMod "save your selections for next time" pattern).
  MT-26: the Master Trainer indexes several table folders at once.
  Every root keeps the same incremental reconcile contract (the
  `(size, mtime_ns)` + sha256 short-circuit per root; the MT-25
  auto-rescan now covers every indexed folder), and the merged
  surface distinguishes tables by the **absolute table key** (index
  root + relative path, native separators; `table_key()`) - the
  relative path remains the documented single-root identity, and key
  lookups resolve casefolded with the documented relative-path
  fallback (`TableIndex.get_by_key` / `RootIndexSet.get_by_key`).
  The folder list persists in `master-settings.json` schema 7 -> 8
  (`table_folders`, primary first, capped at `TABLE_FOLDERS_LIMIT`
  = 8; strict non-empty unique casefolded strings; schema-7
  documents promote on load - the list is filled from the single
  stored last folder and the relative table references (last
  table, recents, pins) are re-anchored to absolute table keys
  under it, so pins / recents survive the upgrade; a schema-7
  document carrying the field is refused as an unknown field; a
  schema-8 document with a set last folder but an empty list
  self-heals to the single folder). The tables index document
  carries one checksum-bound root block per indexed folder (schema
  1 -> 2; `save_index_set` / `load_index_set`; schema-1
  single-root documents promote on load). The folder lifecycle is
  `MasterApp.add_folder` / `remove_folder` / `move_folder_front`
  (named `ValueError`s; `set_folder` keeps its replace-all
  contract), managed by the "Folders..." header button - the
  folder manager window (the indexed folders in user order, the
  primary marked with a star; "Add folder..." / "Set primary" /
  "Remove" / "Close"; every action re-scans the indexed roots,
  saves the index, restarts the auto-rescan clock and refreshes
  the view; a failed change lands in the status line, fail-closed).
  The waiting view gains the **Folder column** (the entry's index
  root), and the row key becomes the absolute key in a multi-root
  session - picker, details, pins, recents and the MT-24 analysis
  queue are all key-based. `run_master` multi-root folder
  resolution: an explicit folder argument wins as the primary root
  with the stored folders indexed behind it (casefold-deduped,
  each printed as an "Also indexing stored folder:" line); a
  parameterless start keeps the stored folder list as-is (a
  missing stored folder stays visible as a scan problem, fixed
  through the folder manager); only a genuinely first start / no
  stored folders shows the directory picker (a cancelled first
  start exits 0); every stored folder gone shows the picker (the
  pick is prepended as the new primary, a cancel keeps the missing
  list); an explicit missing folder is the documented exit-2
  refusal. Zero load-path effect - the MT-9 gate re-checks the
  table file under its index root independently at load time. Zero
  catalog effect (no table-parsing change). Remaining candidates
  (evaluated, not yet adopted): per-table notes / tags (organize
  metadata) - the documented 0.35 candidate; the MT-21
  multi-column trainer grid; the game launch integration (needs
  install-path data). +44 tests (7 in
  `tests/test_native_master_state.py`: the schema-8
  `table_folders` round-trip, the schema-7 document promotion
  (folder list from the stored last folder + the re-anchored
  relative table references), the schema-7-carries-the-field
  unknown-field refusal, the schema-8 self-heal, and the cap /
  unique / non-empty named refusals; 37 in
  `tests/test_native_master_ui_mt26.py` new: the `RootIndexSet`
  pure surface (roots / add / remove / move-front, the
  first-root-wins merged lookups, the key resolution with the
  relative-path fallback, the read-only merged entries, the
  `table_key` form), the multi-root `MasterApp` (the folder
  lifecycle + named refusals, the persisted folder list, the
  schema-2 index-set round trip, the per-root reconcile
  independence, the missing-root scan problem), the key-based load
  paths (`request_load` / `choose` across roots, the cross-root
  same-relative-path disambiguation), the folder manager window
  (primary marker, the add / set-primary / remove wiring, the
  auto-rescan clock restart), the Folder column + the row key, the
  table-load picker labels, the `run_master` multi-root folder
  resolution, the multi-root auto-rescan); full main suite 4,543
  OK / 30 expected skips (4,499 from the 0.33 content + 44 new);
  catalog remeasure `blocked-catalog-034-mt26` (3-chunk deep-equal
  audit over the 151 reference tables, 2026-11-09): 151/151
  loaded, 0 load errors, 117,809 total / 116,756 supported /
  60,161 staged / 103,607 actionable / 12,974 headings / 1,053
  blocked - **zero delta** vs `blocked-catalog-033-auto-rescan`
  (per-table count/reason/sha changes: 0); feature matrix
  unchanged (42/42, 7,475/7,475 over
  `w4b4-case30-20261020081722Z`); AP-11 0/6,143. VERSION 0.34 +
  CHANGELOG entry in the same change. The 0.34 build
  `native-20261109T024143Z-a5457911` cut from `main` @ `dc00343`
  (2026-11-09): in-build suite 4,543 OK / 30 expected skips,
  `ce_inputs: []`, `runtime_unverified` deliberately kept per gate;
  source ZIP `CT2Trainer-0.34-source.zip` sha256
  `0d0a0849a90171f64eaf5b55ec06ec1d9117d02d5330895dcb4279e26f73b0f5`
  (14,455,170 bytes), portable ZIP
  `CT2Trainer-0.34-windows-portable.zip` sha256
  `ade1ecc520ddbeaf6886e1b195fc6e2886a5f9cbeaa64b15f9ac5679420f5054`
  (49,719,386 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `606ea2287eb9f787308d862c18209076ee42e4f7a4ae88fcb93bf8f22edcb6f6`,
  16,983,514 bytes, ships next to the converter).
- 0.33 Master Trainer table folder auto-rescan (MT-25)
  (2026-11-08, root-direct on `main`; online-evaluated in
  `master_trainer/ROADMAP.md`, the "0.33 table folder auto-rescan"
  section - WeMod automatic game detection (the front end keeps the
  found-game / content pairing current), game-trainer-manager
  (Karasukaigan) directory watching + auto-import of matching files,
  Cheat Happens Trainer Manager library-freshness lineage).
  MT-25: the waiting view re-runs the existing incremental scan (the
  same `(size, mtime_ns)` + sha256 short-circuit contract as the
  manual Rescan, one stat pass per interval) on a bounded background
  interval (`AUTO_RESCAN_INTERVAL_SECONDS` = 30 s) so added /
  changed / removed tables show up in the index and the view without
  a manual F5. No OS file-watcher API - polling only, cross-platform.
  The persisted on/off flag lives in the master state
  (`master-settings.json` schema 6 -> 7, `auto_rescan`, strict bool,
  documented default on; schema-6 documents promote on load, a
  schema-6 document carrying the field is refused as an unknown
  field) and is toggled by the status-bar "Auto-rescan: on/off"
  button (next to the attach-mode toggle; re-persists on every
  change; a non-bool change raises the named `ValueError` and lands
  in the status line without a state change). The scan pauses on
  trainer entry (the poll tick early-returns, exactly like the MT-24
  analysis worker) and while a picker is open; the interval clock
  restarts on a manual rescan, a folder change, and the waiting-view
  rebuild (trainer round-trip); the tick runs through `rescan()`, so
  added / changed tables are also re-queued for the MT-24 background
  analysis, and the tick carries no status-line flash (the waiting
  line keeps its cadence). Zero load-path effect - the MT-9 gate
  re-checks the table independently at load time. Zero catalog
  effect (no table-parsing change). Remaining candidates
  (evaluated, not yet adopted): per-table notes / tags (organize
  metadata) vs. the multi-root index (several table folders in one
  Master window) - the 0.34 candidate, decided at the next release;
  the MT-21 multi-column trainer grid; the game launch integration
  (needs install-path data). +16 tests (4 in
  `tests/test_native_master_state.py`: the schema-7 `auto_rescan`
  round-trip, the schema-6 document promotion, the
  schema-6-carries-the-field unknown-field refusal, the non-bool
  refusal; 12 in `tests/test_native_master_ui_mt25.py` new: the
  status-bar toggle (present + on/off text, flips the flag and
  persists it, a failed change lands in the status line without a
  state change), the interval clock (a poll after one interval
  re-runs the incremental reconcile so a newly added table shows up,
  without the "Rescanning…" flash; a disabled flag skips it; trainer
  mode skips it; a manual rescan restarts the clock so no immediate
  second pass)); full main suite 4,499 OK / 30 expected skips
  (4,483 from the 0.32 content + 16 new); catalog remeasure
  `blocked-catalog-033-auto-rescan` (3-chunk deep-equal audit over
  the 151 reference tables, 2026-11-08): 151/151 loaded, 0 load
  errors, 117,809 total / 116,756 supported / 60,161 staged /
  103,607 actionable / 12,974 headings / 1,053 blocked - **zero
  delta** vs `blocked-catalog-032-analysis` (per-table
  count/reason/sha changes: 0); feature matrix unchanged (42/42,
  7,475/7,475 over `w4b4-case30-20261020081722Z`); AP-11 0/6,143.
  VERSION 0.33 + CHANGELOG entry in the same change. The 0.33 build
  `native-20261108T200230Z-b0167049` cut from `main` @ `6e71739`
  (2026-11-08): in-build suite 4,499 OK / 30 expected skips,
  `ce_inputs: []`, `runtime_unverified` deliberately kept per gate;
  source ZIP `CT2Trainer-0.33-source.zip` sha256
  `4528d1d0f2ee269fb2ee7ec470d9e9711b3c284bffe6cf582f7dafa7431756f2`
  (14,433,388 bytes), portable ZIP
  `CT2Trainer-0.33-windows-portable.zip` sha256
  `5e0244791b6f31a2e2219d5c33541c978ca4c0d399c8e7a234cb0c16e8ccb3d7`
  (49,703,149 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `59961d511d3964b075c968a3c577117ffa235970d65976f66d7e34e0eae010a9`,
  16,968,879 bytes, ships next to the converter).
- 0.32 Master Trainer per-table entry count + blocked count
  (background plan analysis) MT-24 (2026-11-06, root-direct on `main`;
  online-evaluated in `master_trainer/ROADMAP.md`, the "0.32
  per-table entry count + blocked count (background plan analysis)"
  section - FLiNG per-trainer "N Options" / option-count metadata,
  game-trainer-manager (Karasukaigan) organize/search workflows,
  Cheat Happens Trainer Manager v2 inspect-before-load lineage).
  MT-24: the waiting-view tree gains two columns between Detail and
  Size - Entries (the actionable record count of the plan compile:
  the supported script / value records, i.e. the real cheat options)
  and Blocked (the blocked record count of the same analysis). The
  analysis runs in the background: one daemon thread
  (`master_trainer/analysis_worker.py`, queue limit 64, dedupe by
  table content sha, only tables with a bound process name are
  queued) through the tested `compile_table` plan path - no Lua
  execution, no target attach, the same static proof the corpus audit
  uses. The columns show "..." while pending and "-" on a named
  compile failure, the counts once analyzed; a blocked count > 0
  appends the bounded "N blocked" note to the detail column after the
  pin marker. Results persist in `table-analysis.json` (schema 1,
  under the state home, keyed by table content sha256, LRU-bounded to
  1024 entries, top-8 blocked reasons per table, 200-char error
  detail) - a content change re-analyzes, an unchanged table reuses
  the cached entry; the pure decision layer is
  `master_trainer/table_analysis.py` (`counts_from_plan` /
  `blocked_reasons_from_plan` / `ok_analysis` / `failed_analysis` /
  `AnalysisStore` with strict key-set + checksum + timestamp + count
  validation, `AnalysisRefusal`). The worker is not auto-started: the
  waiting view owns the lifecycle (start / resume + queue at the end
  of the view build, pause on trainer entry after the attach gate,
  stop + clear on close); the meta line shows the live "analyzing N
  table(s)" figure while the queue has work; the MT-22 table-details
  window gains the analysis block (`table_details.py` `analysis`
  kwarg). Display-side observation only - it never blocks, alters, or
  delays the MT-9 load gate, which re-checks the table independently
  at load time. Zero catalog effect (no table-parsing change).
  Remaining candidate (unchanged): the MT-21 multi-column trainer
  grid. +69 tests (57 in `tests/test_native_master_analysis.py` new:
  the pure counts / reasons builders, the ok / failed analysis
  builders, the store's strict validation (unknown fields, wrong
  sha, bad counts, checksum mismatch), LRU eviction by `analyzed_at`
  with sha tie-break, the refusal codes, and the `active_workers()`
  live-worker registry lifecycle; 12 in
  `tests/test_native_master_ui_mt24.py` new: the column wiring +
  pending / failed / pinned / group-row shaping, the queue discipline
  (unbound tables never queued, rescan re-queues on content change
  only), the details-window analysis rows, the trainer-entry pause,
  the close stop + reference clear, the window-created default worker
  with the real compile path); plus the cross-module test-isolation
  fix (the shared Tk test teardown now stops every live
  plan-analysis worker before releasing the root, so window tests no
  longer leak worker threads into the later engine/timing modules);
  full main suite 4,483 OK / 30 expected skips; catalog zero delta
  `blocked-catalog-032-analysis`
  (3-chunk deep-equal audit over the 151 reference tables,
  2026-11-06): 151/151 loaded, 0 load errors, 117,809 total /
  116,756 supported / 60,161 staged / 103,607 actionable / 12,974
  headings / 1,053 blocked - zero delta vs `blocked-catalog-031-status`
  (per-table count/reason/sha changes: 0). VERSION 0.32 + CHANGELOG
  entry in the same change. The 0.32 build
  `native-20261108T100731Z-a1d311e5` cut from `main` @ `bfcc3a3`
  (2026-11-08): in-build suite 4,483 OK / 30 expected skips,
  `ce_inputs: []`, `runtime_unverified` deliberately kept per gate;
  source ZIP `CT2Trainer-0.32-source.zip` sha256
  `f6cae57590d083e37308bc4a03b1046b8186617bdb0f98c88c9bc324404493d9`
  (14,426,224 bytes), portable ZIP
  `CT2Trainer-0.32-windows-portable.zip` sha256
  `3a7980ba04f60f7cb93edce3cf5c723ba609ff55a00b1f866079101d3b7bc986`
  (49,699,633 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `6dc34408c8e5ecec1c2215c45da27ea22cc5c5ce5a9629267778b172d44d3485`,
  16,966,114 bytes, ships next to the converter). The first build
  attempt `native-20261108T090044Z-5b70a3af` (preserved) failed the
  in-build suite in `test_native_master_ui_mt23` (WinError 32 on a
  fixture unlink while the MT-24 analysis worker still held the file
  open); test fix `bfcc3a3` (the mt23 window tests stop the worker
  via the shared `_stop_analysis` guard before fixture mutations,
  test-only change) + re-run full main suite green on the final
  tree (4,483 OK / 30 expected skips).
- 0.31 Master Trainer per-table live status + color coding +
  status filter MT-23 (2026-11-05, root-direct on `main`;
  online-evaluated in `master_trainer/ROADMAP.md`, the "0.31
  per-table live status + color coding + status filter" section -
  FLiNG per-trainer "Game Version" / "Last Updated" / option-count
  metadata, Game Cheats Manager (dyang886) smart launcher,
  game-trainer-manager (Karasukaigan) organize/search workflows,
  CheatDeck (SheffeyG) Steam Deck launch options - the documented
  MT-7 route). MT-23: the waiting-view Status column shows the
  table's state right now - one bounded stat per visible row per
  render against the index entry (ok / running / changed / missing
  / unreadable, cheapest fact first, live facts outrank the cached
  scan state - the same order the MT-9 gate proves at load time);
  row color coding (amber #e5c07b for changed, red #ff7b72 for
  missing / unreadable - the two tree tags); the persisted
  "Status: all / ok / attention" header cycle (between the view
  button and the filter entry); `master-settings.json` schema 5 ->
  6 (`view_status` - one of `VIEW_STATUS_FILTERS`, mirrored by
  `table_status.VIEW_STATUS_FILTERS`; schema-5 documents promote
  with `view_status=""`, a schema-5 document carrying the field is
  refused as an unknown field); `MasterApp.set_view_settings` gains
  the 4th parameter `status_filter` (validated + re-persisted,
  every existing change point passes the current mode through, so
  sort/view/filter changes never reset the status filter);
  `_visible_tables()` applies the status filter between the query
  filter and the pin float; the meta line gains the active
  `status filter: X` part + the live `attention: N` count (shown
  only when N > 0). The pure decision layer is
  `master_trainer/table_status.py` (row_file_status / row_status /
  row_tag / filter_rows_by_status, ATTENTION_STATUSES,
  VIEW_STATUS_FILTERS - no OS access, no index mutation); the
  in-app `ui_flow_text()` and the reviewable
  `master_trainer/UI.md` document the new header control + the
  live Status column. Deliberately deferred (unchanged
  candidates): the MT-21 multi-column trainer grid, the entry-count
  / blocked-count columns (they need background plan-analysis
  infrastructure). +28 tests (4 schema-6 state in
  `tests/test_native_master_state.py` + 24 in
  `tests/test_native_master_ui_mt23.py` new: the pure layer - the
  live file state per fingerprint, the running-loses-to-attention
  contract, the tag per code, the filter reshaping per mode + the
  named refusal, the constant mirror against the state schema; the
  Tk wiring - the cycle / persist / restore, the other UI changes
  keeping the mode, the live changed / missing flags + tags, the ok
  / attention row shaping, the meta line); full main suite 4,414 OK
  / 30 expected skips; catalog zero delta
  `blocked-catalog-031-status`. VERSION 0.31 + CHANGELOG entry in
  the same change. The 0.31 build
  `native-20261105T080853Z-2e7f50a5` cut from `main` @ `2def12f`
  (2026-11-05): in-build suite 4,414 OK / 30 expected skips,
  `ce_inputs: []`, `runtime_unverified` deliberately kept per gate;
  source ZIP `CT2Trainer-0.31-source.zip` sha256
  `3bab9648208f6ed4cbafa919991cab19c7921597ac2075c5c8b964e17258c0f9`
  (14,398,817 bytes), portable ZIP
  `CT2Trainer-0.31-windows-portable.zip` sha256
  `df5581ec5e8b0c0b99abdf35b914f08ec138b4470234b48c615304419a970839`
  (49,679,202 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `811c0f85c143b632dd182646282ddb32c3293513a665eb62c8055f74f9c89dcb`,
  16,948,380 bytes, ships next to the converter).
- 0.30 Master Trainer table details + live load-gate preview
  MT-22 (2026-11-04, root-direct on `main`; online-evaluated in
  `master_trainer/ROADMAP.md`, the "0.30 table details + load-gate
  preview" section - FLiNG per-trainer version / "Last Updated"
  metadata, game-trainer-manager organize/search workflows, Game
  Cheats Manager .ct handling FAQ, Cheat Happens Trainer Manager v2
  portable + last-used pinning). MT-22: the waiting-view row
  context menu offers "Table details" first - a read-only Toplevel
  with the indexed facts for the table (path, folder, size,
  modified, bound processes, index status, pin, last used, running
  PIDs, content sha - first 12 hex + "...") plus the on-demand
  `gate_table_for_load` re-check (the same pass MT-9 runs at load
  time; refusal = stable named code + displayable detail - a stale
  / changed / unreadable table is explained at inspection time, not
  only at load time); the pure `table_details.py` row builder
  (`format_size` / `format_mtime` / `gate_line` /
  `table_detail_lines`, named fallbacks); single window (lift on
  second open), transient, non-resizable, closed on trainer entry;
  the only I/O is the bounded gate re-check under the load limit;
  the in-app `ui_flow_text()` and the reviewable
  `master_trainer/UI.md` document the new row-menu entry.
  Deliberately deferred (unchanged candidates): the MT-21
  multi-column trainer grid, the entry-count / blocked-count
  columns, the per-table status / color-coding. +16 tests
  (`tests/test_native_master_ui_mt22.py` new: the pure builder -
  all facts in order, the unreadable entry + named fallbacks, the
  no-bound-processes label, the deduped/sorted PIDs, the size /
  mtime / gate-line formatters with boundaries; the Tk wiring -
  the menu order through a recording `tk.Menu` subclass, the
  details command opening the window for the row, the indexed
  facts incl. the live "OK (loadable...)" gate line, lift on
  second open, trainer-entry close, the named refusal display, the
  last-used timestamp); full main suite 4,386 OK / 30 expected
  skips; catalog zero delta `blocked-catalog-030-details`. VERSION
  0.30 + CHANGELOG entry in the same change. The 0.30 build
  `native-20261104T131114Z-11522f68` cut from `main` @ `2fbca94`
  (2026-11-04): in-build suite 4,386 OK / 30 expected skips,
  `ce_inputs: []`, `runtime_unverified` deliberately kept per gate;
  source ZIP `CT2Trainer-0.30-source.zip` sha256
  `091b379c132e277c19f519705dcccc4c0817e8e7e614e5baf2f14bbe3fe414a3`
  (14,387,690 bytes), portable ZIP
  `CT2Trainer-0.30-windows-portable.zip` sha256
  `f4476bb08e3e65e6db9cd35bfe7a72408a555b8525bd6a10f8b794f943083d54`
  (49,669,933 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `9d0a525a78dfbfffb906261ad42e435c5414cb6cb0189dd78c73910063f67643`,
  16,940,058 bytes, ships next to the converter).
- 0.29 Master Trainer UI/UX revamp MT-19/20 (2026-11-04,
  root-direct on `main`; online-evaluated in
  `master_trainer/ROADMAP.md`, the "0.29 trainer-focus +
  discoverability" section - the user field request of 2026-11-04:
  the waiting table list must shrink/collapse so the trainer items
  get maximum space once a process is identified and the trainer
  attaches, generally more accessible UI, the UI flow documented
  for review). MT-19 trainer-focus mode: the whole waiting view
  lives in one container frame (`MasterWindow._waiting_frame`)
  destroyed on trainer entry - the trainer row grid owns the full
  window, rebuilt whole on the way back; the trainer-constructor
  failure path rebuilds the waiting view before failing the load.
  MT-20 discoverability: the read-only "UI flow" header button
  (the in-app copy of the reviewable `master_trainer/UI.md`, single
  Toplevel, lift on second click, closed on trainer entry), F5
  re-scan from anywhere in the waiting view (no-op in trainer
  mode), the initial table-list focus (arrow keys / Enter work
  immediately), the "Retry load" re-arm in the status bar. The
  reviewable full-flow document `master_trainer/UI.md` ships in the
  source ZIP. Deliberately deferred (documented candidate MT-21,
  separate cycle): the multi-column trainer grid (the single-column
  canvas grid is the validated touch-first design; `ui_rows.py` +
  `ui_layout.py` are pure, exhaustively tested and shared with the
  standalone trainer; a column layout rewrites the pure row model,
  the pagination and the 2-D hit-testing). +13 tests
  (`tests/test_native_master_ui_mt19.py` new: container parenting,
  the collapse through the patched handoff, the constructor-
  failure rebuild, the back-to-master fresh frame, one real-
  `TrainerWindow` case, the flow-document content, the read-only
  Toplevel + lift-on-second-click, the trainer-entry close, the F5
  contract in both modes, the initial-focus spy, the retry-bar
  placement); full main suite 4,370 OK / 30 expected skips;
  catalog zero delta `blocked-catalog-029-trainer-focus`. VERSION
  0.29 + CHANGELOG entry in the same change. The 0.29 build
  `native-20261104T094808Z-50af0517` cut from `main` @ `de3e4ff`
  (2026-11-04): in-build suite 4,370 OK / 30 expected skips,
  `ce_inputs: []`, `runtime_unverified` deliberately kept per gate;
  source ZIP `CT2Trainer-0.29-source.zip` sha256
  `2f5ce6e446f8d9885cd653580b5e194a2a0fc524eba7b5f684fe1f1a0e1da3d4`
  (14,378,934 bytes), portable ZIP
  `CT2Trainer-0.29-windows-portable.zip` sha256
  `98c63c368bc2cccd68335e9db94a3b897abbbb815730c97912e3068805fad226`
  (49,667,528 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `88e6ee99aa4c46973945e462ca956977e9942a1e8b30630aa2570107540f2de8`,
  16,937,063 bytes, ships next to the converter).
- 0.28 Master Trainer pinned/favorite tables MT-18 (2026-11-03,
  root-direct on `main`; online-evaluated in
  `master_trainer/ROADMAP.md`, the 0.27 follow-up research - VGC
  Shelf "sort, pin, archive"; the adopted 0.28 candidate).
  `master-settings.json` schema 4 -> 5 (`pinned_tables` - relative
  table paths, most recent pin first, capped at
  `PINNED_TABLES_LIMIT` = 25, each a non-empty string within the
  table-path length bound); schema-4 documents promote on load
  with `pinned_tables=[]`, a schema-4 document carrying the field
  is refused as an unknown field (the same discipline as
  MT-11/15/16); the pure `table_filter.pin_tables` reshaping of
  the already-sorted-and-filtered row set (never adds or drops
  tables: pinned rows first in pin order, casefolded comparison,
  the remainder keeps the input order, pin paths not in the row
  set ignored); the row context menu "Pin to top" / "Unpin"
  (`MasterApp.set_table_pinned` validates with named `ValueError`s
  - cap / already pinned / not pinned - and re-persists
  immediately); a pinned table floats to the top of the list view
  and to the top of its process group in the grouped view (pin
  applied after filter + sort, before the MT-17 grouping); the pin
  marker lives in the detail column, the first column stays the
  bare relative path (row identity). +15 tests
  (`test_native_master_state.py` +4,
  `test_native_master_table_filter.py` +4,
  `tests/test_native_master_ui_mt18.py` new +7). Full main suite
  4,357 OK / 30 expected skips. Catalog remeasure
  `blocked-catalog-028-pin` (chunked 64x3 audit over the 151
  reference tables, 2026-11-03): 151/151 loaded, 0 load errors,
  117,809 total / 116,756 supported / 60,161 staged / 103,607
  actionable / 12,974 headings / 1,053 blocked - zero delta vs
  `blocked-catalog-027-view` (per-table count/reason/sha
  changes: 0); feature matrix unchanged (42/42, 7,475/7,475 over
  `w4b4-case30-20261020081722Z`); AP-11 0/6,143. The 0.28 build
  `native-20261103T161621Z-ea8fde2f` cut from `main` @ `d7f4cf0`
  (2026-11-03): in-build suite 4,357 OK / 30 expected skips,
  `ce_inputs: []`, `runtime_unverified` deliberately kept per gate;
  source ZIP `CT2Trainer-0.28-source.zip` sha256
  `13f4b2222a83f9e4588d388b4120beaf8018a091a05364029ae2a950c0dabb1a`
  (14,363,765 bytes), portable ZIP
  `CT2Trainer-0.28-windows-portable.zip` sha256
  `d656835a69ece75ff6adaa5ce766385327fb9ec08d89837ad772425dafe91ce3`
  (49,658,473 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `c12dcea5bb8a609dae4df36f44827ab5269c9e1015cb723067ed98dc100bf99b`,
  16,929,732 bytes, ships next to the converter).
- Latest verified release: 0.31, build
  `native-20261105T080853Z-2e7f50a5` (cut from `main` @ `2def12f`,
  2026-11-05), in-build suite 4,414 OK / 30 expected skips,
  `ce_inputs: []`, `runtime_unverified` deliberately kept per gate;
  source ZIP `CT2Trainer-0.31-source.zip` sha256
  `3bab9648208f6ed4cbafa919991cab19c7921597ac2075c5c8b964e17258c0f9`
  (14,398,817 bytes), portable ZIP
  `CT2Trainer-0.31-windows-portable.zip` sha256
  `df5581ec5e8b0c0b99abdf35b914f08ec138b4470234b48c615304419a970839`
  (49,679,202 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `811c0f85c143b632dd182646282ddb32c3293513a665eb62c8055f74f9c89dcb`,
  16,948,380 bytes, ships next to the converter); superseded 0.30,
  build `native-20261104T131114Z-11522f68` (cut from `main` @
  `2fbca94`, 2026-11-04), in-build suite 4,386 OK / 30 expected
  skips,
  `ce_inputs: []`, `runtime_unverified` deliberately kept per gate;
  source ZIP `CT2Trainer-0.30-source.zip` sha256
  `091b379c132e277c19f519705dcccc4c0817e8e7e614e5baf2f14bbe3fe414a3`
  (14,387,690 bytes), portable ZIP
  `CT2Trainer-0.30-windows-portable.zip` sha256
  `f4476bb08e3e65e6db9cd35bfe7a72408a555b8525bd6a10f8b794f943083d54`
  (49,669,933 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `9d0a525a78dfbfffb906261ad42e435c5414cb6cb0189dd78c73910063f67643`,
  16,940,058 bytes, ships next to the converter); superseded 0.29,
  build `native-20261104T094808Z-50af0517` (cut from `main` @
  `de3e4ff`, 2026-11-04), in-build suite 4,370 OK / 30 expected
  skips,
  `ce_inputs: []`, `runtime_unverified` deliberately kept per gate;
  source ZIP `CT2Trainer-0.29-source.zip` sha256
  `2f5ce6e446f8d9885cd653580b5e194a2a0fc524eba7b5f684fe1f1a0e1da3d4`
  (14,378,934 bytes), portable ZIP
  `CT2Trainer-0.29-windows-portable.zip` sha256
  `98c63c368bc2cccd68335e9db94a3b897abbbb815730c97912e3068805fad226`
  (49,667,528 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `88e6ee99aa4c46973945e462ca956977e9942a1e8b30630aa2570107540f2de8`,
  16,937,063 bytes, ships next to the converter); superseded 0.28,
  build `native-20261103T161621Z-ea8fde2f` (cut from `main` @
  `d7f4cf0`, 2026-11-03), in-build suite 4,357 OK / 30 expected
  skips,
  `ce_inputs: []`, `runtime_unverified` deliberately kept per gate;
  source ZIP `CT2Trainer-0.28-source.zip` sha256
  `13f4b2222a83f9e4588d388b4120beaf8018a091a05364029ae2a950c0dabb1a`
  (14,363,765 bytes), portable ZIP
  `CT2Trainer-0.28-windows-portable.zip` sha256
  `d656835a69ece75ff6adaa5ce766385327fb9ec08d89837ad772425dafe91ce3`
  (49,658,473 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `c12dcea5bb8a609dae4df36f44827ab5269c9e1015cb723067ed98dc100bf99b`,
  16,929,732 bytes, ships next to the converter); superseded 0.27,
  build `native-20261103T145543Z-b29b3688` (cut from `main` @
  `8aa0815`, 2026-11-03), in-build suite 4,342 OK / 30 expected
  skips,
  `ce_inputs: []`, `runtime_unverified` deliberately kept per gate;
  source ZIP `CT2Trainer-0.27-source.zip` sha256
  `264b42d6c42dac1bb434c1d0591e82ac0bec69e61e1a1c75047c6aa58126f40e`
  (14,357,294 bytes), portable ZIP
  `CT2Trainer-0.27-windows-portable.zip` sha256
  `bfcf2abc885122dfa8653fcfd0046323e7112f59c0850958688e36e014ebc135`
  (49,654,613 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `9762c8bdc2298c16bd82779f206d9a885a449261a6428187c3bd2155fc5bf1bc`,
  16,929,639 bytes, ships next to the converter); superseded 0.26,
  build `native-20261103T112811Z-59a6b3d5` (cut from `main` @
  `c114ec2`, 2026-11-03), in-build suite 4,320 OK / 30 expected
  skips,
  `ce_inputs: []`, `runtime_unverified` deliberately kept per gate;
  source ZIP `CT2Trainer-0.26-source.zip` sha256
  `3d62f80cdfb95d8439d4a2f2150002976795faad313fa75d47aeb4fb92bb49bd`
  (14,348,462 bytes), portable ZIP
  `CT2Trainer-0.26-windows-portable.zip` sha256
  `49be1d286999ed175737edb073c5ab83533c40cccc7e636685a256a0b07004b3`
  (49,653,968 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `895f937ed5c228c09b97edba28aa9dc4ad228abd58585f73080f40ab265bc031`,
  16,925,677 bytes, ships next to the converter); superseded 0.25,
  build `native-20261103T062439Z-f4c16be9` (cut from `main` @
  `a861bfb`, 2026-11-03), in-build suite 4,259 OK / 30 expected
  skips,
  `ce_inputs: []`, `runtime_unverified` deliberately kept per gate;
  source ZIP `CT2Trainer-0.25-source.zip` sha256
  `64f8c3082cff50687b1962234c17a82e2a2f0c19eb1112ece06a0a25132f35be`
  (14,324,774 bytes), portable ZIP
  `CT2Trainer-0.25-windows-portable.zip` sha256
  `774266f7e2c9dc69f4d8cfc963309b9907442ec6b5343ff629b9e30c04049653`
  (49,633,196 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `8736f73e762b57a8f337bf8fa04c2c16f8622c4d99e7dd7f2167b2c9999e3d8f`,
  16,912,561 bytes, ships next to the converter); superseded 0.24,
  build `native-20261102T102029Z-fe358e35` (cut from `main` @
  `a2777ed`, 2026-11-02), in-build suite 4,193 OK / 30 expected
  skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per
  gate; source ZIP `CT2Trainer-0.24-source.zip` sha256
  `dfdd8cfcca90a2789bf544d8f8de4e34941067feeb2b32ce8d550f98e5bc4eb6`
  (14,298,696 bytes), portable ZIP
  `CT2Trainer-0.24-windows-portable.zip` sha256
  `12262cf16e906c3811ade0a8c582b7a1057c834a3110aff004dfd13b3067e7ab`
  (49,618,009 bytes); superseded 0.23, build
  `native-20261101T145310Z-a160bae4` (cut from `main` @ `6e3ec98`,
  2026-11-01), in-build suite 4,176 OK / 30 expected skips,
  `ce_inputs: []`, `runtime_unverified` deliberately kept per gate;
  the 0.23 Master Trainer roadmap release (MT-6/MT-7/MT-8/MT-9 +
  waiting-view observability + ask-on-first-start folder parameter +
  the placeholder-heading and SC2 hotkey-bridge field fixes); source
  ZIP `CT2Trainer-0.23-source.zip` sha256
  `3360cab031cb1334dda71bb02a511170a9a70d1f583b5a8721624f46e24da464`
  (14,291,040 bytes), portable ZIP
  `CT2Trainer-0.23-windows-portable.zip` sha256
  `eec023ba09e8fcb80608736896f0477f4a783034046e6ad67514e96ed0a2905b`
  (49,609,916 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `e5822f688c653242a9f64bd92e4ba92529d485b89c11607cf20d32e728ca3c20`
  16,895,048 bytes ships next to the converter). Superseded 0.22,
  build `native-20261101T075049Z-f32c112d` (cut from `main` @
  `2b24a1c`, 2026-11-01), in-build suite 4,061 OK / 30 expected
  skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per
  gate; the 0.22 FO4 field-fix cycle release - bounded automatic re-arm of
  ScanMiss enable failures (30 s x 10 attempts, budget reset per
  (re-)attach, armed set survives target exit) + manual Try again /
  Re-attach actions (merge `a12a0b6`, +17 tests, zero catalog delta
  `blocked-catalog-022-rearm`; SC2 0.19 hotkey-bridge field findings
  recorded, fixes deferred to the next field-fix cycle); source ZIP
  `CT2Trainer-0.22-source.zip` sha256
  `c5db1b92c8851d4937e2544a77bd0787c5d48c941ebcfef8741cf4ae104ac7cf`
  (14,243,974 bytes), portable ZIP
  `CT2Trainer-0.22-windows-portable.zip` sha256
  `f89cd0225b5d439bf18106728c3a89e906e56957fd28b9b7b2b5e16f5c3c221a`
  (33,023,506 bytes). Superseded 0.21, build
  `native-20261031T211046Z-14707e12` (cut from `main` @ `9a725a8`),
  in-build suite 4,044 OK / 30 expected skips, `ce_inputs: []`,
  `runtime_unverified` deliberately kept per gate; the 0.21 feature
  release - RT-5 complete (item B CheatCodes code-patch plan path +
  item E messageDialog safe logged no-op; catalog remeasure
  `blocked-catalog-020-rt5-be`: 117,809 total, 116,756 supported,
  1,053 blocked, 60,161 staged, 0 load errors, zero newly blocked)
  plus the Master Trainer (MT-1..MT-5, 141 tests, zero catalog
  effect); source ZIP `CT2Trainer-0.21-source.zip` sha256
  `9dacb4093cd8a7f0444fed9ed7ae9aed6f82c14132ee4f3197b1fb5747580a13`
  (14,231,850 bytes), portable ZIP
  `CT2Trainer-0.21-windows-portable.zip` sha256
  `0701d507701cb2952e1e35e1357bac4b459b38fe87e6811b6b272f2a2c3acaaa`
  (33,010,077 bytes). Superseded 0.20.1, build
  `native-20261031T104114Z-d64ae4c2` (cut from `main` @ `080128c`),
  in-build suite 3,854 OK / 26 expected skips, `ce_inputs: []`;
  the release-content re-cut of the 0.20 branding-icon release (0.20
  changelog suite line corrected to the verified in-build numbers +
  `blocked-catalog-020-icons` remeasure cited; no code or asset
  changes); catalog remeasure `blocked-catalog-020-icons` zero delta vs
  `blocked-catalog-019-field`. Superseded 0.20
  `native-20261030T184820Z-b9d6dc07` (cut from `main` @ `6298803`),
  in-build suite 3,854 OK / 26 expected skips, `ce_inputs: []`; ships the
  user-provided branding icons (`CT2Trainer_Generator` on the tool EXE via
  PyInstaller `--icon` + `window_icon_path("converter")`; `Standalone_Trainer`
  embedded in the `CT2Trainer-Template` stub so every generated trainer
  carries it via `window_icon_path("trainer")`; 1024x1024 PNG masters
  committed, multi-size ICOs rebuilt, `tests/test_native_icons.py` +4);
  the first 0.20 cut (`native-20261030T183527Z-8f2cb20a`) was cut from the
  wrong branch (duplicate 0.19 ZIPs without icons) and deleted; superseded
  0.19 `native-20261030T121918Z-c72dbb38` (cut from `main` @ `fbe626f`),
  in-build suite 3,850 OK / 26 expected skips, `ce_inputs: []`;
  ships the 0.19 field-fix cycle (Sinking City 2 hotkey-bridge AV fix,
  value-read observability, `describe` CLI, South of Midnight
  staged-options support with two-level cascade proof, tap guard and
  moAlwaysHideChildren row suppression; +24 tests) on top of the 0.18
  content; catalog remeasure `blocked-catalog-019-field` zero delta vs
  `blocked-catalog-rt5d-main`; superseded 0.18
  `native-20261028T131208Z-55922918` (cut from `main` @ `70c5a61`),
  in-build suite 3,767 OK / 25 expected skips, `ce_inputs: []`;
  ships the trainer UI row-details window on top of the 0.17 content;
  superseded 0.17 `native-20261027T094839Z-ec6c6f55` (cut from
  `main` @ `ee41630`, in-build suite 3,692 OK / 25 expected skips,
  `ce_inputs: []`) which ships the RT-4.2 runtime provider model (last
  RT-4 package; catalog
  remeasure `blocked-catalog-rt42-main`: 1,351 -> 1,053 blocked of
  117,634, 298 rows unblocked, zero newly blocked, 28 reason-only
  changes) plus the RT-4.3 address-expression & identifier-dialect
  merge, the RT-4.5 and RT-4.6 merges, the trainer UI Scripts view and
  row context menu, and the RT-5 item G / F gate ratifications on top
  of the 0.16.4 content; superseded 0.16.4
  `native-20261024T003853Z-a8cf04fc` (in-build 3,479/25, Sinking City
  2 crash-observability field fix on top of the 0.16.3 content) and
  superseded 0.16.3
  `native-20261023T065015Z-afbc3eba` (in-build 3,421/25, user-tested,
  field finding: Sinking City 2 silent trainer death) and superseded
  0.16.2 `native-20261022T160328Z-0423fb21` (in-build 3,415/25,
  user-tested, field finding: Sinking City 2 activation failure) and
  superseded 0.16.1 `native-20261021T161241Z-b0566a25` (in-build
  3,412/25, user-tested, field finding: Sinking City 2 startup block)
  and superseded 0.16 field-fix re-cut 2
  `native-20261021T123801Z-8c5c4e1e` (in-build 3,405/25, user-tested,
  field finding: Sinking City 2 table-load warnings) and re-cut
  `native-20261020T150115Z-c426fb92` (in-build 3,398/25, user-tested,
  field findings: one cheat = table/build mismatch, state-lock orphan
  after a blocked close).
- 0.16 field-fix round 2 (2026-10-21, branch `native-0.16-lock-selfheal`):
  state-lock self-repair and reliable restart — close() completes when
  blocked and the target is gone (lock/session released, wishes kept),
  atexit session/lock release on a provably gone target, actionable
  stale-lock refusal with assessment reasons and one probe retry; 7 new
  regression tests, local suite 3,405 OK / 25 expected skips. Built as
  `native-20261021T123801Z-8c5c4e1e` (in-build 3,405/25, `ce_inputs:
  []`); the field finding "Inf Items" is a table/build mismatch (no
  code change).
- 0.16.1 field-fix round (2026-10-21, branch `native-0.16.1-sc2-warnings`):
  Sinking City 2 table-load warnings made accurate — table-version
  reference 45 → 46 (CE 7.5 writes 45; v46 field-verified, 13 of the 30
  pinned tables are v46), `{$LUA}` warning now states the built-in Lua
  runtime path, external-action warning split per API (ShellExecute =
  documented safe no-op, messageDialog = real review flag);
  `tests/test_native_sc2_table_warnings.py` (7 tests) + version
  assertion moved to reference 46. Versioning rule (user decision):
  every build gets a new version number, bug fixes bump the patch —
  VERSION 0.16 → 0.16.1 (first build under the rule). Built as
  `native-20261021T161241Z-b0566a25` (in-build 3,412/25, `ce_inputs:
  []`).
- 0.16.2 field-fix round (2026-10-22, branch
  `native-0.16.2-sc2-state-recovery`): Sinking City 2 startup block
  from the 0.16.1 field test (debug log 2026-10-21, trainer
  `4b6b2825f4296e83`, log `The Sinking City 2 (0.16-3).ct2debug.log`):
  WP-57 hook journals persist `captured_placeholders`, which the
  recovery assessment's journal schema (`recovery.py::_hook()`)
  rejected as unknown fields — every placeholder-capture journal
  blocked recovery behind a stale `state.lock`, so the trainer refused
  to start; the field is now an optional journal field validated
  with the writer-side contract
  (`patterns.validate_placeholder_captures`); malformed captures keep
  the named refusal. +2 regression tests
  (`tests/test_native_recovery.py`); local suite 3,414 OK / 25 expected
  skips; build pending (patch bump to 0.16.2 under the versioning
  rule).
- 0.16.3 field-fix round (2026-10-22, branch
  `native-0.16.3-sc2-field`): Sinking City 2 activation failure from
  the 0.16.2 field test (debug log 2026-10-22, trainer
  `4b6b2825f4296e83`, log `The Sinking City 2 (0.16-4).ct2debug.log`,
  x64 controller / x64 target): (a) recovery brick - the 0.16.2 fix
  added only `captured_placeholders`; the sibling writer field
  `value_data_ranges` on every allocation entry (persisted since
  WP-47/55 `ee07b60`) still failed `_hook()` schema validation, so
  every allocation-bearing journal blocked recovery behind the stale
  `state.lock`; it is now an optional field validated with the
  writer-side contract (<=4096 exact {address,size} spans,
  in-allocation bounds, no duplicate span). (b) module-snapshot retry -
  `ERROR_BAD_LENGTH` was mislabeled as 24 (real 1116; 24 =
  ERROR_INVALID_ID, the transient code observed 9 ms after attach while
  the game was still loading DLLs); now a bounded 8-attempt
  exponential-backoff retry on {1116, 24, 119}, architecture-aware
  native-only fallback flag (0x10 for 32-bit targets), both failure
  codes in the dual-failure message. +4 (`tests/test_native_architecture.py`)
  +2 (`tests/test_native_recovery.py`) regression tests; local suite
  3,421 OK / 25 expected skips; cut as 0.16.3 build `native-20261023T065015Z-afbc3eba` (in-build
  suite 3,421/25, `ce_inputs: []`, `runtime_unverified` kept per
  gate; VERSION + __version__ in the same change per the
  versioning rule; source ZIP sha256
  `0b34c4f3797095aefcba66a45d46216596e816817ea1b98208a42a5217df2e5a`,
  portable ZIP sha256
  `bb495a6f61538051b8caeac14394bdc80b7b165b946f34f3ae710524e37fd0a3`).
- 0.16.4 field-fix round (2026-10-24, branch
  `native-0.16.4-sc2-field`): Sinking City 2 silent trainer death from
  the 0.16.3 field test (debug log 2026-10-23, PC2: trainer pid 10528
  died mid wish-restore after the TALENTPTR aobscan 18:49:31 with zero
  follow-up events; the 18:50:06 restart was refused by the state lock
  while the game was still alive; session 12692 at 19:16 after a game
  restart restored TALENTPTR, proving the restore is not
  deterministically broken): the root cause is missing crash
  observability in the windowed build (unattached stderr, no
  excepthook/faulthandler, unguarded Tk poll callback) - the silent
  death is a hard exit, not a Python failure. Fix:
  `TrainerDebugLog.arm_crash_reporting()` (process-wide
  `sys.excepthook` wrapper `trainer-crashed`, `threading.excepthook`
  wrapper `trainer-thread-crashed` with thread name, `faulthandler` on
  a dedicated append handle independent of `close()`; re-arm closes
  the previous handle; no armed-event noise), `run_trainer` arms it
  for both entry points, `TrainerWindow.poll` wraps `engine.poll()`
  fail-closed (`poll-crashed` + engine block + tick keeps scheduling),
  and the restore loop logs `restore-entry-start` per wish before
  enable. State-lock behavior unchanged. +8 regression tests
  (`tests/test_native_sc2_crash_observability.py`); local suite 3,479
  OK / 25 expected skips; cut as 0.16.4 build
  `native-20261024T003853Z-a8cf04fc` (in-build suite 3,479/25,
  `ce_inputs: []`, `runtime_unverified` kept per gate; VERSION +
  __version__ in the same change per the versioning rule; source ZIP
  sha256 `87e1f448ce3a9b72386b62ffb8c981e451242c3bf88ecb030e9979c29733e47f`,
  portable ZIP sha256
  `ffa08832fe0f6673ef00054c15395990846a67a709a6d19c9e78becad35d6807`).
- Trainer UI feature (2026-10-24, branch
  `native-0.17-ui-script-inspector`, user request): (a) new `Scripts`
  filter view (sixth chip; lists every `kind == "script"` record -
  blocked and unselected included with their reason, headings and
  value rows hidden; `FILTER_CHIP_COLUMNS_WIDE` 5 -> 6, the narrow 2x3
  grid is now exactly full); (b) row context menu on right-click or
  the existing 400 ms long-press (the long-press now opens the menu
  instead of the Info dialog directly) with "Script preview" (raw
  Auto Assembler / embedded Lua / global program source, or the
  normalized enable/disable operation list, read-only), "Copy script
  text" (clipboard), "What is happening here" (deterministic
  plain-language assessment from plan metadata: status, staged gate
  with provider labels, program form with phase operation counts and
  capabilities, one-shot, provides/requires, depends-on/required-by,
  activation set, source hotkeys, runtime verification) and
  "Details" (the existing Info dialog, content unchanged); pure text
  builders in the new `src/ct2trainer/native/ui_script_view.py` (no
  Tk), design in `documentation/trainer-ui-design.md` section 8. 25
  new tests (`tests/test_native_ui_script_view.py` +23,
  `tests/test_native_ui_rows.py` +2 Scripts-view filter tests,
  `tests/test_native_ui_layout.py` `window_columns` 5 -> 6); local
  suite 3,587 OK / 25 expected skips; catalog remeasure
  `blocked-catalog-ui-scripts` zero delta vs
  `blocked-catalog-rt45main` (UI-only change). Ships in the 0.17
  build, cut after the remaining RT-4.x merges (RT-4.2 1,085) per the
  user decision 2026-10-24.
- Trainer UI row-details window (2026-10-28, main commit `a731619`,
  user request, VERSION 0.17 -> 0.18): right-click / long-press on a row
  now offers "Row details" leading the context menu - a single read-only
  900x700 Toplevel combining the raw script source (static Auto Assembler
  / embedded Lua / global program / normalized operation list), the
  plain-language assessment (what it does / what is known) and the
  concrete actions the trainer performs for the entry (enable/disable
  operations, capabilities, CE Lua API calls extracted from embedded-Lua
  sources, memory writes for value rows, group-activation cascade for
  flagged group headings); new pure builders `entry_actions` /
  `row_details` / `lua_apis_used` in `ui_script_view.py` (display-only
  CE-API vocabulary, no runtime dependency), context-menu wiring
  refactored to the unit-testable `_context_menu_items` in `ui.py`, the
  existing script-preview / assessment / details items unchanged; 22 new
  tests (`tests/test_native_ui_row_details.py`); main suite 3,767 OK /
  25 expected skips; cut as 0.18 build
  `native-20261028T131208Z-55922918` (in-build suite 3,767/25,
  `ce_inputs: []`, `runtime_unverified` kept per gate; source ZIP
  sha256 `3d8612ed97dbfb80a4c4fc95f9899852285ac184a738a03932bc9fad240ed967`,
  portable ZIP sha256
  `9e4080e07b33f3b2a3a97178891916b711955b96f9b0fa6139a6b120fea3b9ca`).

## Historical evidence

- [Archived goal and integration ledger](archive/TRACKING-history.md) —
  Wave 1–4 gap tables, case registry, work-package decisions and merge log.
- [Archived plans](archive/README.md) — completed AP/WP designs.
- [Progress ledger](../documentation/native-progress.md) — build and
  acceptance evidence.
- [CE trainer-behavior assessment](../documentation/ce-feature-parity-assessment.md)
  — capability map and full-corpus method.
