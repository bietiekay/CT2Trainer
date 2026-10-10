# Native semantic denominator (AP-10)

**Run:** `repo-reproducible` · **Status:** 0.9.0-rc2 baseline (2026-10-10)
**Artifacts:** `gap_inventory/inventory.json` (13 pinned tables) and
`gap_inventory/gap-report.json` (13 pinned tables, record-exact).
**Method:** pure static XML analysis (stdlib, Python 3.12) of the CT
structure under `TableReferences/` (repo root) —
strictly read-only, no execution of CT-Lua/AA, no target-process
interaction, no Git/network commands. All ratings are syntax assumptions;
`unknown` stays `unknown`.

## 1. What the denominator is

**Expected actions** are the records of a table that are supposed to
produce a game effect — i.e. all non-group `CheatEntry` entries **minus**
navigation:

```
expected_actions = records − navigation
```

- `navigation` = records with null/empty base address (null-array
  placeholders without their own effect) plus pure heading groups. They are
  counted **separately** and **never** reinterpreted as successful cheats.
- `groups` (GroupHeader entries) do not count as record actions. A group
  only counts as an additional action (`group_toggle_actions`) when it has
  a checkbox and forwards a CE built-in effect through
  `moActivateChildrenAsWell` / `moBindActivation` onto a record with its
  own effect (mirrors `_group_has_builtin_on_effect` from
  `src/ct2trainer/table.py`).
- `one_shot` (missing/empty `[DISABLE]` section) remains an expected
  action, but is carried as `locked` with `one_shot_save_contract` because
  no OFF/save contract exists. No fictitious OFF contract is invented.
- Status values: `statically_assumed` (static syntax/structure assumption
  only), `locked` (needs a concretely missing API/feature), `unknown`
  (unknown, not reinterpreted).
- **Synthetic vs. static vs. real effect separation:** fixture/mock
  evidence (e.g. own fixture EXE, Lua mock) is *synthetic* and does not
  count as game effect. `statically_assumed` means "structurally
  plausible", not "works". Real, observed game effect is measured
  exclusively in the Windows/Deck tests (AP-11) and is by definition **0**
  in this lane.

## 2. Start corpus: 13 pinned tables

SHA-256 (full values in `gap-report.json → pinned_tables[]`):

| Table (origin) | Case file (relative to TableReferences) | SHA-256 (short) |
| --- | --- | --- |
| Trine 2 | `case-01.ct` | `56e56c59…` |
| Fallout 4 | `case-02.ct` | `40cda827…` |
| Yooka-Laylee | `case-03.ct` | `ca277a97…` |
| Disco Elysium | `case-04.ct` | `8756f8d2…` |
| Alien Isolation | `case-05.ct` | `d413b6e1…` |
| Resident Evil 2 | `case-06.ct` | `99dcd678…` |
| Borderlands 3 | `case-07.ct` | `bb1250ac…` |
| Clair Obscure Expedition 33 | `case-08.ct` | `5c9f1fef…` |
| Silent Hill Townfall (Steam) | `case-09.ct` | `329fb2ef…` |
| Senua's Saga Hellblade 2 | `case-10.ct` | `d65385d0…` |
| Red Dead Redemption 2 | `case-11.ct` | `615baf32…` |
| Silent Hill Townfall (rml) | `case-12.ct` | `19b34a49…` |
| Resident Evil 4 | `case-13.ct` | `2621c99a…` |

The case file names are neutral; the mapping to the original table
identities above is recorded in `TableReferences/README.md`. The 6
byte-pinned reference hashes from
`tests/fixtures/reference-inventory.json` (case-10, case-11, case-09,
case-06, case-13, case-12) were verified against the corpus: **all 6 hash
and entry-count checks passed** (`reference_verification_all_ok: true`).

## 3. Count results

Pinned start corpus (13 tables, 5 967 records, 0 navigation):

- **Expected actions: 5 967** · groups: 1 269 · group-toggle actions: **0**
- Status: 5 455 locked (91.4%) / 479 statically_assumed (8.0%) / 33
  unknown (0.6%)
- Categories: value_freeze 3 098 · one_shot 1 722 · string_write 731 ·
  persistent_script 413 · custom_value 3

Top-10 gaps on the pinned denominator (share of 5 967):

| # | Gap ID | Label | Records | Share | Requirement |
| --- | --- | --- | --- | --- | --- |
| 1 | `cross_record_symbol` | Cross-record symbol resolution | 3 365 | 56.39% | N-07 |
| 2 | `lua_host_profile` | Lua host profile (bounded host profile) | 1 907 | 31.96% | N-01 / N-19 |
| 3 | `one_shot_save_contract` | One-shot without ON/OFF save contract | 1 722 | 28.86% | State contract (AP-04) |
| 4 | `lua_symbol_api` | Lua symbol API | 190 | 3.18% | N-07 / N-19 |
| 5 | `lua_ce_engine_api` | CE-Lua engine API | 35 | 0.59% | N-19 |
| 6 | `aa_directive_unverified` | Unverified AA directives | 31 | 0.52% | AP-02 |
| 7 | `async_lifecycle` | Async record lifecycle | 23 | 0.39% | N-08 |
| 8 | `lua_worker_thread` | Lua worker threads | 10 | 0.17% | N-15 |
| 9 | `dropdown_link` | DropDown link | 9 | 0.15% | N-18 |
| 10 | `managed_method_resolution` | Managed method resolution (IL2CPP) | 8 | 0.13% | N-12 / N-13 / N-14 |

The rest corpus is empty in the current pinned 13-table corpus
(`corpus_rest` in the gap report reports zero tables); the table above
covers the full pinned denominator.

## 4. Per-CT-ID capture (report structure)

`gap-report.json → pinned_tables[]` contains per table:

- `table_flags` (Forms, table Lua, Custom Types, embedded files,
  UserdefinedSymbols, CheatCodes/structures)
- `main_initialization` (conservative heuristic: table Lua dominates;
  otherwise the first top-level script record, otherwise the first script
  record in document order — **no** semantic main proof)
- `architecture` (hint from filename tokens, module references and
  exclusive 64-bit register/`qword` lines; SSE and 32-bit registers are
  valid in both architectures and deliberately do **not** count — fixes
  an earlier SSE-conditional `mixed` misreport; `unknown` without
  signal)
- `records_by_group[]` → per record: `id, name, type, category, status,
  gaps, providers, lifetime, architecture, target_build, semantics,
  depth, parent, async, address_kind`
  - `type`: `value | string | aa_script | aa_script+lua | script_lua |
    custom | unknown`
  - `category`: `navigation | value_freeze | string_write |
    custom_value | one_shot | persistent_script | configuration |
    unknown`
  - `target_build`: `build_bound_fixed_address | module_binding:<module>
    | managed_module_binding | process_relative | table_symbols |
    process_portable | unresolved | no_own_target`
  - `providers`: statically required capabilities (e.g.
    `typed_value_readwrite`, `pointer_chain`, `aob_scan_process`,
    `string_codec_bounded`, `lua53_host`)
- per-table `counts` (types, categories, statuses, gaps, expected
  actions)
- `groups[]` (checkbox, ON effect, toggle status, descendant records)
- `top_gaps` (per table)

### Address and AA classification (conservative rules)

- Address kinds: `null` → navigation; fixed hex → `statically_assumed` +
  `build_bound_fixed_address`; `$process` → `process_base`;
  `module.dll!Method` → locked `managed_method_resolution`;
  `+N`/`+N*M` (relative, including scaling like `+1*4`, supported by the
  native `address_expression.py`) → assumed; module(+RVA) → assumed;
  symbol (not user-defined) → locked `cross_record_symbol`; user-defined
  symbol → assumed; empty/unrecognized → `unknown`. Hex offsets
  (`+10D8`) are stripped before symbol extraction so offset digits do not
  count as cross-record symbols.
- AA directives: `aobscan[aobscanmodule|aobscanchunk|aobscanregion]`,
  `alloc`, `dealloc`, `align`, `db/dw/dd/dq`, `define`, `label`,
  `registersymbol`, `unregistersymbol`, `readmem`, `reassemble`,
  `globalalloc` → syntax assumption. Locked: `luacall` (arguments
  additionally checked against CE-Lua API patterns),
  `createthread/threadwait`, `getprocaddress*/getmodulehandle`,
  `disassemble`, `autoassemble`, `protect/unprotect`. Unknown residual
  tokens → `aa_directive_unverified` → record `unknown`.
- `globalalloc`: literal-only until a globalalloc symbol is referenced in
  code lines (then locked `aa_globalalloc_general`).
- `createThread(`/`createTimer(` in the Lua branch are capabilities
  (worker/timer), **not** a gap.
- `one_shot`: missing or empty `[DISABLE]` section → `locked` +
  `one_shot_save_contract` (no fabricated OFF/save contract).
- `main_initialization` name matching uses word boundaries so "No
  **Reload**" does not count as the main script.

## 5. Conservative decisions

1. **Traversal glitch fixed:** the first lane version only visited
   top-level records and lost all records nested under GroupHeaders (e.g.
   re2: 1 instead of 312). The traversal now mirrors the product
   `visit()` from `src/ct2trainer/table.py` exactly (every level,
   `GroupHeader == "1"` comparison exact).
2. **Group-toggle rule** mirrors `_group_has_builtin_on_effect`: only
   `moActivateChildrenAsWell`/`moBindActivation` counts as activation
   (not `moDeactivateChildrenAsWell`); result in the 13 tables: **0**
   (RDR2 has exactly one activation group whose children only
   deactivate).
3. **String addresses** with a foreign symbol or a managed binding are
   `locked` (wrongly `unknown` before); empty/unrecognized addresses stay
   `unknown`.
4. **SSE registers** (`movss/movsd/comiss`) are no 64-bit signals;
   32-bit registers/`dword` are valid in x64 — neither counts as an
   architecture signal.
5. **Parse errors** are tracked in the inventory, not silenced; the
   original format is preserved (the current pinned corpus has 0 parse
   errors).
6. **Duplicate IDs** are reported, not repaired — repair is the
   CE/product side's concern.
7. **Architecture** is a hint, not attach evidence; `unknown` without
   signal (e.g. Alien Isolation).
8. **No goal claim:** all numbers are upper bounds from static analysis.
   Without real game tests, the confirmed fulfillment stays **0%**.

## 6. The 90% goal is NOT reached

Explicitly: the required 90% fulfillment is **not** reached. Confirmed
actions (with real game-effect evidence): **0 of 5 967**. Even the most
generous `statically_assumed` reading (479 records, 8.0% of the pinned
denominator) is not fulfillment — it has no runtime evidence.

**Missing gates (each hard, not substitutable):**

1. Real game installs/builds of the 13 pinned tables (no installation
   exists in this repository).
2. Actual game effect: ON/OFF, values, freeze, target/controller
   restart, saved wishes, errors/pending, cleanup — per concretely
   available build state (AP-11).
3. VM/clean-PC gate without CE/Python (portable converter start, Unicode
   path, rights/UAC, debugger conflict).
4. Real Steam Deck with Proton prefix: x86/x64 APIs, debug events,
   touch/on-screen keyboard, state/freeze/clock, exit.
5. Per-table completeness (Forms, table-Lua lifecycle, Custom Types,
   embedded assets).
6. Frozen/binary evidence: this lane delivers **source-only evidence**;
   the currently tested binary state must not be separated from the
   source state.
7. Reproducibility with exact commands and pinned inputs (see section 7 and `tests/test_native_repro_chain.py`).

## 7. Reproducibility

- Driver: `tools/corpus_denominator/` (repo package, stdlib only).
- Invocation:
  ```powershell
  python tools\corpus_denominator\__main__.py `
      --corpus TableReferences --output <output-dir> --run-id repo-reproducible
  ```
  or as a package: `python -m tools.corpus_denominator --corpus … --output … --run-id …`.
  Default run ID: `repo-reproducible`.
- Inputs: corpus files (hashes per table in
  `inventory.json → tables[].sha256`) +
  `tests/fixtures/reference-inventory.json` (byte-pinned fixture).
- With identical inputs and the same run ID all artifacts are
  byte-identical; the only run-specific field pair is
  `generated`/`run_id` (schema: `run <id>`). The committed
  `gap_inventory/` artifacts are reproduced byte-for-byte by
  `tests/test_native_repro_chain.py` (denominator → feature matrix →
  AP-11 manifest, same run ID `repo-reproducible`).
- Python 3.12, stdlib only.
