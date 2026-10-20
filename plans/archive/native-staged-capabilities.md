# CT2Trainer — "Staged Capabilities" Work Package (PRAGMATA-class tables)

**ARCHIVED** — Historical plan retained for reference.


**Historical plan — WP-14 complete.** Released in 0.10; the original design,
measurements, and session notes below are retained as history. Current
project status is maintained in [TRACKING.md](../TRACKING.md). Future
reference-table work will be scoped in the active
[reference-table-100-roadmap.md](../reference-table-100-roadmap.md).

Original baseline: `main` @ `b6c48cc` (0.9.0-rc2, suite
2617 OK / 25 skips) · Working branch for this cycle: **`native-0.9-staged`**
(created from latest `main`; the `analysis-ce75` branch and untracked
`analysis/` dir referenced here belonged to the user's local CE7.5
comparison work and were deleted 2026-10-11 after the comparison was
consolidated, reviewed and scrubbed).

**Incorporated as an active session goal on 2026-10-11** (goal id recorded in
the session). The user-provided text below is preserved as given; the tail of
the test plan is truncated in the transmitted copy (see note before §16) and
§16 is reconstructed from the repository's own documented commands.

## 0. Historical notes and original read order

- Read order for the receiving session: `AGENTS.md` →
  `plans/archive/native-implementation-continuation.md` → this plan →
  `documentation/native-progress.md`, `native-runtime.md`,
  `native-verification.md`, `build.md`.
- Every number below was **measured** against the code state on 2026-10-10
  and is reproducible with the commands in §16.
- Clean-room rule (non-negotiable): no CE implementation code may be
  referenced, copied or ported into CT2Trainer sources, tests, docs or
  plans. The public `.CT`/XML format contract and *documented behaviour* may
  be derived. The user's CE 7.5 checkout at
  `C:\Users\xboxl\code\cheat-engine-7.5` is an **authorised behavioural
  reference only** (e.g. to confirm what `moHideChildren` does to the UI) —
  conclusions may be cited as behaviour, never code.
- The attached table `C:\Users\xboxl\Downloads\PRAGMATA.CT` is
  **reference input only**. It is never added to the repo or distributed.
  Its behaviour is captured by a new synthetic corpus case (clean-room rule:
  `TableReferences/` contains synthetic tables with documentation-level
  origin mapping only).

## 1. Original problem statement (resolved by WP-14)

PRAGMATA.CT (opencheattables.com, CE 7.6+, 7526 lines, **595 `CheatEntry`
nodes**) is a "multi-step" table: most elements are only usable **after** an
AA/Lua script has run, because the script resolves a base address at runtime
(AOB scan / registerSymbol) and the elements underneath reference that
symbol. In CE, these top-level nodes are collapsed/locked
(`moHideChildren`), the user activates the script, and only then the child
options "unfold" and become live.

Running the current converter on this table (`ct2trainer native prepare
PRAGMATA.CT --process PRAGMATA.exe --architecture x64`) yields:

| Metric | Value |
| --- | --- |
| Total records | **595** |
| Supported | **162** |
| Blocked | **433** (73%) |

Blocking reasons (from the generated plan JSON, `blocked_reasons` +
per-entry `reason`):

| Root cause | Reason string | Records |
| --- | --- | --- |
| **RC-1** script parent with child-activation options → hard block | `Parent/child activation propagation is unsupported.` | **14** (all top-level "Get app.X" / feature scripts) |
| **RC-2** cascade from RC-1: children reference symbols provided by the blocked parent | `Required symbol has no unique supported provider: <sym>.` (22 distinct symbols: `InventoryManager_addr`, `EnhanceManager_addr`, `EnemyBattleSystem_addr`, `HackingManager_addr`, `i_base_*_addr`, `i_min_hp_value`, `ptrCapture_INJECT_GET_CURRENT_HP_347018`, `i_base_gravirty_addr`, `i_training_mode`, `vf_target_ctime`, `chk_max`, `skip_overwrite`, `vc_min_*`, …) | **≈409** |
| **RC-3** signed `<Offset>` literal rejected by parser | `Pointer offset must be a hexadecimal integer literal.` | **10** (all descendants of one parent that uses `<Offset>+28</Offset>`) |

**RC-1 is the root of the 73% blockage.** In CE, the "Get app.X"
top-level records are *script records with nested child records and
propagation options* (`moHideChildren` / `moActivateChildrenAsWell` /
`moDeactivateChildrenAsWell`). CT2Trainer's tested parent/child activation
model (AP-07 stage 3: `activation_policy.py`, `parent_flags.py`,
`compiler.py`, engine `_enable_parent`/`_disable_parent`) is currently
**only applied to `GroupHeader` navigation headings**; any *non-heading*
record with children + propagation options is fail-closed
(`compiler.py` L442–444). Because the parent script is blocked, its
`registersymbol(...)` providers are dropped (`_block()` clears `provides`),
so ~409 descendant records lose their symbol provider and cascade into "no
unique supported provider".

## 3. Behaviour contract (derived from PRAGMATA usage + CE 7.5 behaviour
reference, clean-room)

Behavioural facts used as the contract source (no code copied):

1. **Collapsed until active:** `moHideChildren` — children of such a record
   are not exposed/expandable while the record is inactive (CE 7.5
   address-list behaviour: "if not active then don't allow expanding").
   → In the trainer: a script-backed group node shows only its toggle; its
   children appear (via group navigation) but in **staged/pending** state
   until the script is active.
2. **Activation propagation:** `moActivateChildrenAsWell` = parent ON also
   activates children; `moDeactivateChildrenAsWell` = parent OFF deactivates
   explicitly-active children; both = children follow the parent
   unconditionally; neither = plain grouping. The existing flag classes map
   exactly: both → `required_dependency`, activate-only →
   `direct_activation`, deactivate-only → `collective_off` (already
   implemented + tested for headings in `activation_policy.py`/
   `parent_flags.py`).
3. **Runtime-resolved symbols:** a script registers symbols at activation
   (`registersymbol` AA directive / Lua `registerSymbol`) and unregisters
   them at deactivation. Records referencing such a symbol are **staged**:
   unavailable while the provider is inactive, live while it is active.
4. **Staged value records** (CE value children under a script parent) have
   no memory effect of their own when "activated" — activation means
   *availability* (readable/writable/freezable). Provider OFF ⇒ staged
   children must stop being freezable (freeze released, value shown as
   unavailable).
5. **Master toggle:** an embedded-Lua record that flips a known set of
   record IDs on/off by ID is, in the trainer, a **master switch** that
   applies that set through the engine's normal activation path (dependency
   order respected) — not a re-execution of the CE-coupled Lua.

Derived CT2Trainer contract (what this work package implements):

- **C1 (staged capability):** any supported record whose address requires a
  symbol provided by another supported record is *staged*: plan carries
  `staged` metadata; engine gates read/write/freeze on provider liveness
  (named, fail-closed error while provider inactive); UI shows pending state
  with the provider's name and unlocks automatically when the provider
  becomes active.
- **C2 (script-parent cascade):** the tested flag-class contract from AP-07
  stage 3 extends from group headings to **script records with children**
  (value parents with flags stay fail-closed, named). Engine cascade ON
  activates the provider script first, then children; OFF releases frozen
  staged children first, then deactivates the provider. Save boundary
  unchanged (only confirmed ON wishes persist; value children have no
  wishes, so OFF only releases freeze).
- **C3 (activation sets):** the converter statically extracts enable/disable
  record-ID sets from embedded `{$lua}` blocks (pattern:
  `getMemoryRecordByID(<int>)` + `Active = true|false`, uniform direction per
  section, all IDs must exist in the table). Plan carries
  `activation_sets`; a record with a non-empty `activation_sets` gets its
  enable/disable routed through the engine's set application (dependency
  ordered) **instead of** executing the CE-coupled embedded Lua. Extraction
  is fail-closed: any ambiguity → no metadata, record keeps its ordinary
  Lua profile.
- **C4 (signed offsets):** `<Offsets>` values accept an explicit sign
  (`+`/`-`), hex semantics unchanged (`+28` = `0x28`). Malformed forms
  (`++10`, `+`, `0x`, decimal `x`) stay rejected fail-closed.
- **C5 (visibility/UX):** staged records are *included by default* in the
  trainer (they are supported, only gated at runtime); converter UI shows
  capability `Staged` with the provider in the details column; trainer UI
  shows the pending state and auto-unlock (see §8).

## 4. Plan schema changes (schema stays `2`, additive)

Per entry, new optional fields:

```jsonc
// record whose address needs a symbol provided by another entry
"staged": {
  "provider_ids": [11],                 // supported entries providing all required symbols (1..n)
  "provider_labels": ["Get Lunafilament / others amount (menus)"]
}

// record whose embedded Lua statically declares ID activation sets (C3)
"activation_sets": {
  "enable": [1, 2, 11, 18, 24, 25, 27, 21, 604],
  "disable": [258, 247, 568, "..."],
  "source": "lua-static-extract"        // always this constant; never inferred at runtime
}
```

- Both plan validators (compiler `validate_plan` and engine
  `validate_plan`) **re-derive** both fields from `requires`/`provides` and
  the entry XML and refuse tampering (same pattern as
  `parent_relations` re-derivation, compiler.py L946–967).
- `staged` is present only when all required symbols are uniquely provided
  by supported entries; otherwise the entry stays blocked as today.
- Old 13 corpus tables: none currently produce `staged`/`activation_sets`
  in a way that changes bytes — **verify by per-table plan diff**
  (§11, step 4); the old run-id artifacts are not invalidated for tables
  whose plans are byte-identical.

## 5. Feature-matrix / gap-inventory extension

Three new gap labels (add to `tools/corpus_denominator/__main__.py`
`GAP_LABELS`, `classify.py`, and `feature_matrix.py` `FEATURES`; the
`feature_contract_complete` consistency list grows from 36 → 39 labels,
total features 39 → 42 including the 3 gate features):

| New gap label | Label text | Requirement |
| --- | --- | --- |
| `signed_pointer_offset` | Signed pointer-offset literal (`+`/`-` in `<Offsets>`) | format contract (this package) |
| `script_parent_activation` | Script parent with child-activation propagation (staged unlock) | this package (extends AP-07) |
| `record_activation_set` | Embedded-Lua master toggle (record-ID activation sets) | this package |

Classifier detection rules (static, no execution):

- `signed_pointer_offset`: any `<Offset>` text matching `[+-][0-9a-fA-Fx]`.
- `script_parent_activation`: record kind `script` with children and any of
  `moActivateChildrenAsWell`/`moDeactivateChildrenAsWell`/`moBindActivation`
  in `<Options>`.
- `record_activation_set`: embedded Lua containing `getMemoryRecordByID(`
  **and** `.Active = true` or `.Active = false`.

The `cross_record_symbol` feature note is extended to document the new
staged runtime gating (evidence: new tests in §10). No AP-11 gate rules
change.

## 6. Corpus input: `TableReferences/case-14.ct` (synthetic, clean-room)

Origin (documentation-level only): *Pragmata (opencheattables.com table,
CE 7.6+)*. Module token: **`ct2synth14.exe`**.
`CheatEngineTableVersion="46"`. All names/bytes synthetic; scripts use only
already-supported directives (`aobscanmodule`, `alloc`/`dealloc`,
`registersymbol`/`unregistersymbol`, `db`, `nop`, `mov`, plain labels) so
the table compiles without target-specific proof.

Entry spec (IDs as in the file; ≈57 `CheatEntry` nodes total):

| ID | Description | Kind | Key attributes | Purpose |
| --- | --- | --- | --- | --- |
| 0 | `"Toggle scripts"` | AA script `Async="1"` | embedded `{$lua}`: ENABLE — `getLuaEngine().menuItem5.doClick()`, `getLuaEngine().Close()` inside `synchronize(...)`, then loop over IDs `{2,6,8,11,14,25}` doing `getMemoryRecordByID(id).Active = true` + `addressList.refresh()`; DISABLE — same loop with `Active = false` | C3 activation-set pattern + CE-engine-API fail-closed reference |
| 1 | `"Get synth.Manager"` | AA script | `aobscanmodule(SynthAnchor,ct2synth14.exe,<16 fixed bytes>)`, `registersymbol(SynthAnchor)` / DISABLE `unregistersymbol` | plain symbol provider (baseline, no children) |
| 2 | `"Set min bullet num"` | AA script | `Options moActivateChildrenAsWell="1" moDeactivateChildrenAsWell="1"`; `registersymbol(synth_min_addr)`; child values 3–5 | **C2: script parent, `required_dependency`** |
| 3 | `"min"` | 4 Bytes | `Address=synth_min_addr` | staged child |
| 4 | `"min #2"` | 4 Bytes | `Address=synth_min_addr+4` | staged child + relative offset |
| 5 | `"min #3"` | 4 Bytes | `Address=synth_min_addr+8` | staged child |
| 6 | `"Get gravity (readonly)"` | AA script | registers `synth_gravity_base`; child 7 | C1 provider with offset chain |
| 7 | `"CurrentGravityRate"` | Float | `Address=synth_gravity_base`, `Offsets [0x130]` | staged child, deep offset |
| 8 | `"Set gravity"` | AA script | registers `synth_gravity_set`, `synth_gravity_flag` (with `dd 0` defaults); children 9–10 | provider with two symbols |
| 9 | `"Set?"` | 4 Bytes | `Address=synth_gravity_flag` | staged child |
| 10 | `"Target value"` | Float | `Address=synth_gravity_set` | staged child |
| 11 | `"Training: target time"` | AA script | `Options moActivateChildrenAsWell="1"` only; registers `synth_training_base`, `synth_training_mode`; children 12–13 | **C2: `direct_activation` on a script parent** |
| 12 | `"mode"` | 4 Bytes | `Address=synth_training_mode` | staged child |
| 13 | `"target"` | Float | `Address=synth_training_base` | staged child |
| 14 | `"Get synth.EnhanceManager settings"` | AA script | `Options moHideChildren="1" moDeactivateChildrenAsWell="1"`; `registersymbol(EnhanceManager_addr)`; child 15 | **PRAGMATA EnhanceManager shape: collapsed script parent + `collective_off`** |
| 15 | `"base"` | 8 Bytes | `Address=EnhanceManager_addr`, `Offsets [0]`; child 16 | pointer chain root |
| 16 | `"_EquipmentPerkMainGame -> _BootingPerks"` | GroupHeader | `Address=+18`, **`Offsets [0, +28]`** (signed offset), children 17–24 | **C4: signed offset parent (RC-3 shape)** |
| 17 | `"<RepairKitCapacity>k__BackingField"` | 4 Bytes signed | `Address=+60` | staged |
| 18 | `"<MainGadgetCapacity>k__BackingField"` | 4 Bytes signed | `Address=+64` | staged |
| 19 | `"<AssaultGadgetCapacity>k__BackingField"` | 4 Bytes signed | `Address=+68` | staged |
| 20 | `"<ActiveSkillCapacity>k__BackingField"` | 4 Bytes signed | `Address=+74`; child 21 | staged + nested provider parent |
| 21 | `"Skip slot capacity writeback"` | AA script (nested) | `registersymbol(skip_overwrite)` | **nested provider inside a propagation subtree** |
| 22 | `"<PassiveSkillCapacity>k__BackingField"` | 4 Bytes signed | `Address=+78`; child 23 | staged |
| 23 | `"Skip slot capacity writeback"` | AA script (nested) | *requires* `skip_overwrite` (consumer of 21's symbol) | nested provider/consumer pair |
| 24 | `"_RequestedRefreshManagedPerkUnit"` | Byte | `Address=+7C` | staged |
| 25 | `"Get synth.InventoryManager"` | AA script | `Options moHideChildren="1" moActivateChildrenAsWell="1" moDeactivateChildrenAsWell="1"`; `registersymbol(InventoryManager_addr)`; child 26 | **PRAGMATA inventory shape: deep tree, both flags** |
| 26 | `"base"` | 8 Bytes | `Address=InventoryManager_addr`, `Offsets [0]` | |
| 27 | `"ItemSlotTable"` | GroupHeader | `Address=+30`, `Offsets [0]` | |
| 28 | `"List<SynthItem>"` | GroupHeader | `Address=+10`, `Offsets [0]` | |
| 29 | `"_items"` | GroupHeader | `Address=+10`, `Offsets [0]` | |
| 30–37 | `"[i] [SynthItem]"` (i = 0…7) | GroupHeader | `Address=+10+20*i` (hex relative), each with children 38+ | 8 inventory slots (PRAGMATA has 89; 8 keeps the table tractable) |
| 38–53 | `"_ID"` / `"_Quantity"` per item | 4 Bytes | `Address=+10` / `+14` under each item header | **16 staged leaf values** (the bulk of the staged denominator) |
| 54 | `"synth table / CE 7.6+"` | GroupHeader (plain, `moHideChildren`) | children 55–56 | |
| 55 | `"YesNo"` | DropDownList | `DisplayValueAsItem="1"`, choices `0:No` / `1:Yes` | dropdown coverage inside the new case |
| 56 | `"FAST_BOOST_PLUS_30"` | AA script | ENABLE only (byte write at `ct2synth14.exe+40`), empty/missing DISABLE | one-shot shape under a plain heading (existing contract, pins interaction with new code) |

Corpus plumbing updates (same lane, one commit):

1. `TableReferences/case-14.ct` — the table above.
2. `TableReferences/README.md` — mapping row: origin *Pragmata
   (opencheattables.com table, CE 7.6+)*, token `ct2synth14.exe`, measured
   SHA-256.
3. `tools/corpus_denominator/__main__.py` — `PINNED` += `case-14.ct`
   (14 tables).
4. `tests/fixtures/reference-inventory.json` — add `case-14.ct` reference
   entry (sha256, table_version 46, cheat_entries = final count,
   assembler_scripts, table_lua_blocks 0, pointer_offsets incl. signed,
   hotkeys 0, async_scripts 1, dropdown_links 0).
5. `tools/corpus_denominator/classify.py` — the three new gap-label
   detections (§5).

## 7. Completed work packages (original scope, files, acceptance)

Shared-file rule (AGENTS.md §4): `engine.py`, `compiler.py`, `memory.py`,
`hooks.py`, `lua_host.py`, `ui.py` may be written by **one** agent at a time.
Lane assignments below are chosen so no two lanes write the same file.

### WP-14-A — Compiler & format (Lane B, first)

**Scope:** RC-1 + RC-3 + plan metadata C1/C3.

Files (write access): `src/ct2trainer/native/compiler.py`, new
`src/ct2trainer/native/lua_activation_sets.py`, `src/ct2trainer/native/validate*`
paths inside `compiler.py`.

Changes:

1. `_offsets()`: regex → `[+-]?(?:0x)?[0-9a-fA-F]+` (sign optional on both
   sides; keep length/sign-bound checks; `int(..., 16)` semantics unchanged).
2. Flag-class derivation: lift the heading-only branch — script records with
   children + propagation options get the same `parent_activation` flag
   class; `moBindActivation` on any non-heading parent stays a **visible
   named block** (extend, don't remove, the current refusal message). Value
   records with children + flags stay fail-closed with a named reason
   (documented scope: script parents + headings only).
3. `parent_relations` build (L614–638): include script parents (drop the
   `kind != "heading"` guard for scripts; keep headings).
4. New `staged` derivation after `_dependencies`: for every supported entry
   with non-empty `requires` whose symbols are all uniquely provided, set
   `staged: {provider_ids, provider_labels}` (labels from entry `path`).
5. New module `lua_activation_sets.py`: pure-static parser for embedded
   `{$lua}` blocks — extract `getMemoryRecordByID(<int>)` →
   `Active = true|false` assignments **per `[ENABLE]`/`[DISABLE]` section**;
   adopt only when: all IDs exist in the table, direction is uniform per
   section, IDs unique within the set. Output: `{enable: [...], disable:
   [...]}` or `None`. No Lua execution anywhere in this path.
6. Wire `activation_sets` into plan entries; validator re-derivation +
   tamper refusal in `validate_plan` (both compiler- and engine-side
   validators must check — engine's `validate_plan` currently re-derives
   `parent_relations`; extend the same pattern).

**Tests:** `tests/test_native_compiler.py` (signed offsets, incl.
`+28`/`-0x10`/`+0x28` accepted, `++10`/`+`/`0x`/empty rejected;
script-parent flag classes for all three option combinations +
moBindActivation refusal; `staged` marker present/absent;
`activation_sets` extraction: happy path, unknown-ID refusal,
mixed-direction refusal, no-set-fallback) + update
`tests/test_native_parent_activation.py` compiler section (replace
`test_non_group_parent_flags_stay_refused` with
`test_script_parent_flags_supported`; keep/extend the moBindActivation
non-heading refusal test).

**Acceptance:** old 13 corpus plans byte-identical except documented deltas
(verify per table, §11 step 4); new unit tests green.

### WP-14-B — Engine runtime (Lane C, after WP-14-A merged)

**Scope:** C1/C2 runtime behaviour.

Files (write access): `src/ct2trainer/native/engine.py` only (sole writer
while open).

Changes:

1. Staged gating: `read_value` / `set_value` / `set_freeze` on entries with
   `staged` refuse with a named `NativeRuntimeError` ("Staged record
   '<label>' requires active provider '<provider label>'") while any
   `provider_ids` entry is not in `applied`. Reads during the poll loop must
   treat this as a *state*, not an error log (UI shows pending, not a red
   error).
2. Script-parent cascade: extend `_enable_parent`/`_disable_parent` so
   script parents route through the same `ActivationController` path as
   headings (record kind `RECORD_ACTION`, with `RECORD_ASYNC` for async
   ones — already the mapping at L1226–1229). ON: activate provider script
   first (existing `dependency_ids` ordering already guarantees symbol-first
   activation — verify), then children; staged value children need no
   activation call (availability is derived), but the cascade must *not*
   skip them for state-mirroring purposes. OFF: before `unregistersymbol`,
   release freeze on every frozen staged descendant (extend the current
   "skip value children" behaviour: frozen staged children are unfrozen
   first, visibly, then the provider is deactivated).
3. Save boundary unchanged: ON persists only the requested parent's wish;
   OFF clears the parent wish (value children have no wishes — assert this
   in tests).
4. Re-attach replay: a saved parent wish replays the whole cascade on
   attach (provider before children), existing `desired` replay path.
5. `activation_sets` routing: enable/disable of a record carrying
   `activation_sets` applies the ID set through the normal per-record
   activation path in dependency order (skip already-active; per-record
   failures reported, no silent partial success — same partial-failure /
   safety-hold semantics as the cascade); the CE-coupled embedded Lua is
   **not** executed for such records (documented contract C3).

**Tests:** `tests/test_native_parent_activation.py` engine section
(script-parent ON cascade with staged value children: reads succeed only
after provider ON; OFF releases freeze first; `direct_activation` and
`collective_off` variants for script parents; moBindActivation script parent
refused before any write; replay on re-attach) + new
`tests/test_native_staged_capability.py` (fake memory from
`test_native_engine.FakeMemory`: staged read/write/freeze gated on provider;
provider OFF releases freeze; tampered `staged`/`activation_sets` metadata
refused by `validate_plan`; activation-set application ordering + partial
failure).

**Acceptance:** all engine tests green; no change to existing 22
parent-activation tests' assertions except the documented non-heading
behaviour change.

### WP-14-C — Trainer UI (Lane B, after WP-14-B merged)

**Scope:** C5 for the generated trainer (`src/ct2trainer/native/ui.py`,
`ui_layout.py`).

The trainer UI is card-based with breadcrumb group navigation ("Open group"
= the unfold mechanism). Changes:

1. **Staged card state:** for supported entries with `staged` whose
   provider(s) are not in `engine.applied`: card shows
   `Pending — unlocks with: "<provider label>"`, value shown as
   `unavailable`, Apply/Freeze/step buttons disabled. Provider active →
   normal card (auto-unlock). The existing `poll()` re-render trigger
   (changes to `applied`/`desired`) already covers the auto-unlock; verify
   and, if needed, extend the comparison tuple so a provider's state change
   forces a re-render even when only child availability changes.
2. **Provider OFF while staged children frozen/displayed:** engine releases
   freeze (WP-14-B); UI surfaces the named status text and switches children
   back to pending (no silent state loss — status line shows "provider
   deactivated; staged children unfrozen").
3. **Master-toggle card:** records with `activation_sets` render a single
   prominent toggle ("Apply set / Clear set") calling the engine
   set-application path; `Info` shows the extracted ID list + record labels
   + `source: lua-static-extract`.
4. `info()` (ui.py L163): add staged provider line and activation-set
   details.
5. `ui_layout.py`: any shared card-state helpers for the new states;
   `tests/test_native_ui_layout.py` extended for the new state computation
   (pure functions, no tk main loop).

**Acceptance:** layout tests green; manual smoke: run the built case-14
trainer against the repo's fixture target where feasible
(`tests/windows/fixture_target`), verify pending → unlock → freeze release
visibly.

### WP-14-D — Converter UI (Lane B, after WP-14-A)

**Scope:** C5 for the converter GUI (`src/ct2trainer/native/converter.py`,
`capability.py`).

1. `render()`: capability column gains `Staged` (supported + `staged`
   metadata) between `Supported` and `Blocked`; details column shows
   `Unlocks after: <provider label>` (and `Master toggle: N records` for
   activation sets).
2. `inspect()` status line: `Target x64: N supported (M staged, K blocked)
   records…`.
3. `model["selected"]` keeps staging records included by default (they are
   supported).
4. `capability.py`: add the staged/activation-set signals to the static
   assessment so the review report matches the new plan fields (keep the
   report deterministic).

**Acceptance:** `inspect` on PRAGMATA.CT (user machine or this box) shows
`595 supported` with the staged/blocked split; on the old 13 tables the
table looks unchanged apart from the new count format.

### WP-14-E — Corpus, matrix, artifacts, docs (Lane D, parallel; case-14
draft may start immediately, label definitions need WP-14-A)

**Scope:** §5 + §6 + §11.

Files: `TableReferences/case-14.ct`, `TableReferences/README.md`,
`tools/corpus_denominator/{__main__.py, classify.py, feature_matrix.py,
ap11_campaign.py}` (as needed), `tests/fixtures/reference-inventory.json`,
`gap_inventory/*` (regenerated artifacts),
`tests/test_native_table_completeness.py`, gate tests, docs.

Steps:

1. Author `case-14.ct` per §6; compile it with the new compiler; iterate
   until 100% of its records are supported (staged where expected).
2. Add the three new gap labels to classifier + `GAP_LABELS` + `FEATURES`
   (status `covered` **only after** WP-14-A/B/C evidence exists — evidence
   entries name the test files + modules from §7).
3. Extend `tests/test_native_table_completeness.py`: gate:1 now covers
   **14** pinned tables; for case-14 assert: every source record preserved,
   nested AA scripts under value parents handled, staged leaf values present
   with `staged` metadata, signed-offset parent supported, activation sets
   extracted on ID 0.
4. Regenerate the full denominator chain (exact commands in §11) with a
   **fresh run-id**; the new `gap_inventory/` artifacts commit together with
   the code.
5. Update gate:3 repro-chain test inputs (now 14 tables) and re-pin.
6. Docs: `documentation/native-runtime.md` (staged contract, script-parent
   cascade contract, activation-set contract, signed-offset contract),
   `documentation/native-verification.md` (new gate evidence),
   `plans/archive/native-implementation-continuation.md` (§2 table rows, §5 new
   package status `WP-14`, §8 log entry), `documentation/native-progress.md`
   (ledger entry with measured numbers: 162/595 → new split), `AGENTS.md`
   (corpus 13 → 14 tables, feature matrix 39 → 42), `CHANGELOG.md`
   (0.10 section).

**Acceptance:** artifact consistency checks pass
(`consistency.all_ok == true` in feature-coverage.json), pinned table count
14, expected-action total = old 5967 + case-14 non-navigation records.

## 8. UI/UX specification summary (both apps)

| Surface | Today (PRAGMATA.CT) | After this package |
| --- | --- | --- |
| Converter: Capability column | `Blocked` for ~433 records | `Supported` (~595) with `Staged` for the symbol-dependent ones; `Details` names the provider / master-set |
| Converter: status line | `Target x64: 162/595 records supported` | `Target x64: 595 supported (≈409 staged, 0 blocked)` (residual blocks, if any, individually justified in Details) |
| Trainer: top-level script node ("Get app.X") | n/a (records blocked, no trainer built for them) | normal toggle card; group navigation ("Open group") reveals children |
| Trainer: staged child card | n/a | `Pending — unlocks with: "<parent>"`, controls disabled → auto-unlocks the moment the parent toggle goes ON (poll-driven re-render) |
| Trainer: parent OFF while children frozen | (unsupported) | children visibly unfrozen + status note; provider toggle goes OFF only after freeze release (bottom-up) |
| Trainer: "Toggle scripts" master record | n/a | master switch card applying the extracted enable/disable ID set through the engine (dependency order); `Info` shows the set + source |
| Saved wishes | confirmed ON scripts only | unchanged; a staged child is never a wish, so it is not persisted/replayed independently — its availability always follows the provider |

## 9. Historical test plan (tests completed with WP-14)

| Test file | Change | Proves |
| --- | --- | --- |
| `tests/test_native_parent_activation.py` | `test_non_group_parent_flags_stay_refused` → `test_script_parent_flags_supported`; +script-parent cascade engine tests (all three flag classes, moBindActivation refusal, replay, freeze release) | C2, RC-1 |
| `tests/test_native_staged_capability.py` | **new** | C1: gating, unlock, freeze release, replay, validator tamper refusal for `staged` |
| `tests/test_native_activation_sets.py` | **new** | C3: static extraction (happy/refusal/mixed), plan metadata, engine set application (ordering, partial failure, no Lua execution) |
| `tests/test_native_compiler.py` / `tests/test_native_addresses.py` | extend | C4: signed offset acceptance/rejection matrix; plan stability |
| `tests/test_native_table_completeness.py` | extend to 14 tables + case-14-specific assertions | gate:1 with the new shape |
| gate:2 `tests/test_native_source_frozen_parity.py` | extend fixtures with a staged plan | parity incl. `staged`/`activation_sets` round-trip through `build_trainer`/`read_embedded_plan` |

> [!NOTE]
> The transmitted copy of the handoff document was truncated after this
> point. Sections §10–§15 are not present in the received text (they are
> referenced from §5–§7 as §10/§11). The implementing session follows the
> acceptance criteria in §7–§9 plus the repository's standing protocol
> (`plans/archive/native-implementation-continuation.md`). §16 below is reconstructed
> from the repository's own documented commands.

## 16. Historical reproducibility commands (reconstructed from repository documentation)

```powershell
# Dev environment (once, offline from dependencies/)



& .tools\python\python.exe -m venv .tools\native-build-env
& .tools\native-build-env\Scripts\python.exe -m pip install --no-index --find-links dependencies\native\lupa --find-links dependencies\native\iced-x86 lupa==2.8 iced-x86==1.21.0
& .tools\native-build-env\Scripts\python.exe tools\native_build.py restore-nasm --output .tools\native-tools

# PRAGMATA reference run (reference input only, outside the repo)



$env:PYTHONPATH = (Resolve-Path src).Path
& .tools\native-build-env\Scripts\python.exe -m ct2trainer.native prepare 'C:\Users\xboxl\Downloads\PRAGMATA.CT' --process 'PRAGMATA.exe' --architecture x64 --output <temp-dir>

# Full local test suite



$env:PYTHONPATH = (Resolve-Path src).Path + ";" + (Resolve-Path tests).Path
$env:PYTHONIOENCODING = "utf-8"
$env:CT2TRAINER_NASM = (Resolve-Path .tools\native-tools\nasm.exe).Path
& .tools\native-build-env\Scripts\python.exe -m unittest discover -s tests -p 'test_native_*.py'

# Denominator chain with a fresh run id (WP-14-E step 4).



# Stages 2 and 3 refuse to write into the directory that contains their



# input artifacts, so each stage writes to its own output directory and the



# result is copied into gap_inventory/. Stage 3 must reference the



# committed gap_inventory/feature-coverage.json path so the committed



# manifest's provenance matches the test-side byte-reproducibility rerun.



& .tools\native-build-env\Scripts\python.exe tools\corpus_denominator\__main__.py --corpus TableReferences --output gap_inventory --run-id <fresh>
& .tools\native-build-env\Scripts\python.exe tools\corpus_denominator\feature_matrix.py --gap-report gap_inventory\gap-report.json --inventory gap_inventory\inventory.json --output <tmp2> --run-id <fresh>
Copy-Item <tmp2>\feature-coverage.json gap_inventory\feature-coverage.json
& .tools\native-build-env\Scripts\python.exe tools\corpus_denominator\ap11_campaign.py manifest --gap-report gap_inventory\gap-report.json --inventory gap_inventory\inventory.json --feature-coverage <repo>\gap_inventory\feature-coverage.json --corpus-root TableReferences --output <tmp3> --run-id <fresh>
Copy-Item <tmp3>\ap11-campaign.json gap_inventory\ap11-campaign.json
```

## 17. Implementation deltas and measured results (2026-10-11)

Verified during WP-14-E; superseding the spec values above where noted.

### 17.1 case-14 record 7 signed offset (`+0x130`)

Spec §6 listed record 7 as `Offsets [0x130]`. The authored table writes the
same value with an explicit sign, `<Offset>+0x130</Offset>` (value unchanged,
0x130 = 304), so the `signed_pointer_offset` gap label occurs **at record
level**: the denominator toolchain traces records, and a gap that only
appeared on a group heading would not reconcile with
`gap_traceability`'s record-level trace (report per-table gap counts vs
trace entries). Heading 16 keeps its spec'd `+28` literal, pinning the
heading-chain shape at compiler level; the record-level literal pins the
classifier/denominator path. Measured `signed_pointer_offset` count: 1.

### 17.2 Old-13 plan stability (per-table diff, rc2 → WP-14)

Every old corpus table recompiled with the rc2 compiler (commit `1ea7ed6`)
and the WP-14 compiler (commit `c244232`) and plan-diffed byte-wise:

- 12 of 13 tables: byte-identical plans.
- **case-06.ct (documented delta):** exactly one entry changed — id **17258**
  ("Syn06 Item 17258"), an async Lua/AA record, flipped blocked → supported.
  Old reason: `Static AA envelope: Cannot register a symbol not owned by
  this program: synClockAOB.` The WP-14 Lua symbol-provider extraction
  (`lua_symbol_providers.py`) resolves the table-owned symbol correctly.
  Case-06 plan totals: 331 records, supported 38 → 39, blocked 293 → 292.

### 17.3 Classifier semantics (corpus denominator)

- `assert` added to `SUPPORTED_AA_DIRECTIVES` (`tools/corpus_denominator/
  lib.py`): the product's `aa.py` section parser supports `assert` as a
  guarded-write directive; case-14 record 56 is the first corpus record to
  use it.
- One-shot rule now mirrors the product's `compile_one_shot` contract: an
  ENABLE-only script (missing `[DISABLE]`) classifies as `one_shot` with the
  `one_shot_save_contract` gap when it is guarded (a preceding `assert`, at
  least one `db/dw/dd/dq` write, no symbol registration); unguarded
  ENABLE-only scripts keep `aa_sections_incomplete` / `unknown`. The old 13
  tables contain no affected records (no `assert`, no missing-`[DISABLE]`
  records), so their classification is unchanged. case-14 record 56 is the
  first corpus record in `one_shot` with a *missing* (vs empty) `[DISABLE]`.

### 17.4 Measured results (run `wp14-staged-20261011T093320Z`)

- Pinned tables: **14**; expected actions **6011** (5967 + 44 from
  case-14); gap labels **39**; in-scope features **42** (39 gap features +
  3 gates), all covered; action-weighted denominator **7361** (was 7332).
- `gap_inventory/` artifacts regenerated byte-reproducible; all three
  consistency blocks report `all_ok` (feature-coverage: 13 checks).
- `category_counts` (pinned): `custom_value` 3, `one_shot` 1723,
  `persistent_script` 423, `string_write` 731, `value_freeze` 3131.
- `status_counts` (pinned): `locked` 5475, `statically_assumed` 503,
  `unknown` 33.
- PRAGMATA.CT reference measurement (never added to the repo): **595
  records → 586 supported (416 staged / 170 non-staged), 9 blocked**.
  Residual blocks, each individually justified: 2 records with a strict
  `"$process"` address expression plus an anonymous forward/backward
  assembly label (unsupported address form), 7 `i_base_*` children whose
  provider chain has no unique supported provider in this table.
  `activation_sets` extraction produced no set on this table (fail-closed:
  the master-toggle Lua does not match the uniform static pattern) — the
  record keeps its ordinary Lua profile.

### 17.5 Value-parent scope (confirmed inert)

Value records with children plus propagation flags stay fail-closed with a
named reason (C2 scope: script parents + headings only). No corpus table or
the PRAGMATA reference exercises a value-parent flag record, so the refusal
path stays pinned by unit tests only.
