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
| RT-5 runtime trainer parity | root | in progress (inventory done 2026-10-23; items F+G done 2026-10-26; items A+C done 2026-10-28; item C2 done 2026-10-29; item D done 2026-10-29) | Full API/construct inventory landed as `documentation/rt5-api-inventory.md` (2026-10-23): 394 distinct Lua call names cross-classified (61 CE globals, 36 CE object methods, 28 stdlib, 269 table-local); 20 hosted CE globals, 41 named-refusal gaps split 14 game-facing vs 27 pure-UI no-effect; table-level construct census with per-construct scope decisions (CheatCodes code patches 22 tables/175 entries, embedded .lua loader chain in 4 tables, onOpenProcess/onTableLoad callback dispatch, `Structures` unreferenced, `LastState`/sounds/signatures no-effect); remaining RT-5 implementation items A-G queued in the doc section 9 after the RT-4 lanes. Visual CE UI is outside scope. Item G (`createThread`/`threadWait` backend decision, O22) landed 2026-10-26 (lane `native-rt5-g`, merge `2de9c0e`): decision recorded — option (2), capability gate stays, no thread backend ships this milestone (bounded owned-thread backend awaits a root design review: lifecycle, debug-event ownership, join semantics, exact disable teardown, journal receipt); byte-stable five-stage fail-closed pins in `tests/test_native_rt5_thread_gate.py` (+17 tests: focused 17 OK; main suite 3,648 OK / 25 expected skips after the merge); census re-derived from launch base `blocked-catalog-rt43-main`: exactly 2 O22 rows (Witcher3 4.02HF1_G25v2 + 4.03_G25v2, id 192, "Call Function") and 77 first-word `createThread` usages across 18 tables split into 26 AA directive lines in 8 tables (gate-governed) and 51 Lua-context lines in 11 tables (`lua_host` cooperative workers, separate family, not O22-gated), zero first-word `threadWait` lines; tests only, zero catalog movement (remeasure `blocked-catalog-rt5g-main`: 1,351 blocked of 117,634, zero delta). Item F (no-effect register ratification) landed 2026-10-26 (lane `native-rt5-f`, merge `966fccd`): `tests/test_native_rt5_no_effect_register.py` +22 tests pin the section-8 register as an enforced byte-stable contract (26 CE UI globals keep the exact `Unsupported CE Lua API: <name>` refusal with zero target side effects; section-7.3 object-method register pinned per surface; table-level Structures/Signature/SignedHash/PublicKey/Forms/Files families byte-exact warnings + sorted `ignored_sections`, plan-inert; LastState/RealAddress/Color/Comments silent; GroupHeader supported; ActivateSound/DeactivateSound hotkey children ignored; usemono() exact composite reason); tests-only, zero catalog movement (remeasure `blocked-catalog-rt5f-main`: 1,351 blocked of 117,634, zero delta). Item A (embedded `<Files>` extraction + `findTableFile`/`readStringLocal`) landed 2026-10-28 (lane `native-rt5-a`, merge `479977c`): new `src/ct2trainer/native/embedded_files.py` (CE dual-branch codec — exact `Encoding="Ascii85"` = CE-alphabet Ascii85 + raw deflate + 4-byte-LE size prefix; any other/missing value = CE hex branch, hex -> raw deflate read-until-EOF without size prefix, per `luafile.pas::createFromXML`; 4 MiB per-file transport-tracking bound, 16 MiB table total), fail-closed table-load decode (`_parse_embedded_files`, named `TableError`), plan projection `embedded_files` (casefold-sorted, additive, re-validated by both plan validators, schema-2 only), engine registry (`_embedded_files`/`_embedded_by_name`, case-sensitive exact-name, first-occurrence-wins on tolerated duplicates), Lua surface: `findTableFile`/`FindTableFile` (nil when absent, dual access shapes), `readStringLocal` (token-based, strict UTF-8; deviations pinned: omitted/negative maxsize returns full content, no NUL truncation), `stringstream.*` (per-scope registry, 256-object / 16 MiB bounds), `createTableFile`/`tablefile.delete` fail-closed refusals, stringlist `Text` getter/setter (CRLF-to-LF positional split, empty lines kept) + gmatch bug fix, `load`/`loadstring` string-chunk-only compat wrapper; `tests/test_native_rt5_embedded_files.py` +53 (12-case refusal matrix, P5 + RiftApart end-to-end shapes, codec/plan/table-load contracts); full main suite after the merge 3,745 OK / 25 expected skips (baseline 3,692); catalog remeasure (run `blocked-catalog-rt5a-main`): zero delta vs `blocked-catalog-rt42-main` (151/151 load, 117,634 total, 116,581 supported (60,161 staged), 1,053 blocked, 0 compile errors, 0 newly blocked, 0 reason-changed); the 9 reference files with non-empty `<Files>` (7 distinct games) gain `embedded_files` in their plans, zero blocking-status movement. Item C (bounded process-info Lua API family) landed on 2026-10-28 (lane `native-rt5-c`, commit `0167825`): 11 APIs under the clean-room single-target model (getProcessIDFromProcessName returns the attached pid on plan-process match, else 0; getProcessList single-entry pid->name map; getAutoAttachList inert per-scope singleton stringlist; getOpenedProcessID alias; getSettings inert object; integerToUserData identity; targetIs64Bit pointer width; enumModules single-module answer; disassemble bounded iced in the CE line shape; stringlist_add ordinal; getCEVersion pinned '7.5'), item-A-style allowlist wiring (table-scope read-only names + record-scope functions + syntax-check reads), `tests/test_native_rt5_process_info.py` +23 (14-case refusal matrix, byte-exact disassemble lines, 32-bit behavior on pointer_size=4, zero memory writes on all refusals); full main suite after the merge 3,790 OK / 25 expected skips (baseline 3,767); catalog remeasure (run `blocked-catalog-rt5c-main`): zero delta vs `blocked-catalog-rt5a-main` (151/151 load, 117,634 total, 116,581 supported (60,161 staged), 1,053 blocked, 0 compile errors, 0 newly blocked, 0 reason-changed); 44 of 151 tables reference at least one item-C API; no plan fields, no engine path changes. Item C2 (dynamic addresslist records + custom AA directives) landed on 2026-10-29 (lane `native-rt5-c2`, commit `dbfdcc2`, merge `dde9f04`): createMemoryRecord session journal (synthetic IDs >= 2**31, never persisted, cleared on target exit/close, bounded 4096) via AddressList / getAddressList() / built-in AddressList index; CE MemoryRecord runtime surface (Description/Type/Address with verbatim expression text/Script/Parent cycle + self-parent refusal + grandchild promotion/Child[i] 0-based/Offset + OffsetText[i] bounded writes/Count/Index/OffsetCount/isDynamic/Value vtByte..vtDouble read-write/inert display keys); journal + plan-record OnActivate/OnDeactivate as 'ct2fn:<n>' tokens fired from the owning host with stale-scope containment; plan display mutations session-stored (plan untouched); getCEVersion now the number 7.5 (CE LuaHandler pushnumber parity; item-C string pin superseded); addresslist lookups getMemoryRecord (int = flat 0-based position, str = casefolded description, absent -> nil) + getMemoryRecordByID numeric-string coercion + casefolded ByDescription + Count/MemoryRecord[i] OOB nil + inert selection; registerAutoAssemblerCommand/unregisterAutoAssemblerCommand table-scope custom AA directives (built-in names refused, registry dies with table scope, expansion in prepare_program after nested-assembly inlining, strict no-op without registry, revalidation through validate/preflight/dry_link/link); `tests/test_native_rt5_dynamic_records.py` +27 plus pin updates (test_native_rt5_process_info number pin, test_native_lua record.set helper no-op, test_native_rt5_no_effect_register getMemoryRecord now supported, test_native_table_lua_bootstrap record.set engine refusal, test_native_aa_literals signature); full main suite after the merge 3,817 OK / 25 expected skips (baseline 3,790); catalog remeasure (run `blocked-catalog-rt5c2-main`): zero delta vs `blocked-catalog-rt5c-main` (151/151 load, 117,634 total, 116,581 supported (60,161 staged), 1,053 blocked, 0 compile errors, 0 newly blocked, 0 reason-changed). Item D (`onOpenProcess`/`onTableLoad` callback dispatch) landed 2026-10-29 (lane `native-rt5-d`, commit `fb1253b`, merge `9294bb8`): after a clean table-Lua bootstrap the trainer fires the table's CE callbacks on the table-scope host in the CE sequence (onOpenProcess with the attached target PID as a Lua number, then onTableLoad with the Lua literal false - documented bounded deviation: the once-per-attach bootstrap has no before-load phase); each callback in one pcall-wrapped chunk with the argument injected as a literal (no string injection; the chunk uses only stdlib, no table-scope allowlist change), 'absent'/'ok'/'error: <msg>' -> no event / table-callback / table-callback-error, throwing callback contained with plan['table_lua'] byte-identical (the clean bootstrap stays clean for the dependent record scripts), the second callback still dispatches, idempotent per confirmed attach with re-attach re-fire on the fresh scope, refused or failed bootstraps skip the dispatch; `tests/test_native_rt5_table_callbacks.py` +9; full main suite after the merge 3,826 OK / 25 expected skips (baseline 3,817); catalog remeasure (run `blocked-catalog-rt5d-main`): zero delta vs `blocked-catalog-rt5c2-main` (151/151 load, 117,634 total, 116,581 supported (60,161 staged), 1,053 blocked, 0 compile errors, 0 newly blocked, 0 reason-changed). |

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
  151 load, 116,581 supported (60,161 staged) and 1,053 blocked of
  117,634 plan entries; zero load errors (0.20 branding cycle remeasure,
  2026-10-30, run `blocked-catalog-020-icons`, frozen manifest
  `gap_inventory/reference-manifest.json`; zero delta vs
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
- Latest verified release: 0.20.1, build
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
