# CE 7.5 vs CT2Trainer — comparison and analysis

> **Baseline note:** 0.21 cycle (main, 2026-10-31). Final numbers
> refreshed by the release cycle: RT-5 item B (CheatCodes code-patch
> plan path) added the 175 `CodeEntry` records of the 22 CheatCodes
> tables as supported `code_patch` plan entries, and item E landed the
> `messageDialog` safe no-op decision. Catalog remeasure
> `blocked-catalog-020-rt5-be` (2026-10-31): 117,809 total, 116,756
> supported, 60,161 staged, 1,053 blocked, 0 load errors — zero delta
> apart from the +175 code-patch entries.

Status: 2026-10-31, **final** CE 7.5 vs CT2Trainer
comparison. Evidence sources: the repository's own tracking and
inventory artifacts (cited inline), the CE 7.5 local source tree at
`C:\Users\xboxl\code\cheat-engine-7.5` (read-only behavior reference;
file:line cited where a CE behavior claim is verified), and the local-only
reference-table catalog artifacts (named, never reproduced — the original
tables never enter Git). No number in this document is invented: every
count traces to a cited artifact or a cited CE source location.

## 1. Executive summary

CT2Trainer is a clean-room, independently implemented converter and
trainer for Cheat Engine 7.5 `.CT` tables. It compiles a `.CT` table plus
an exact game-process EXE name into a **plan** that a native trainer
engine executes against a pinned single target process. No CE code,
binary, or original-table content is used anywhere in the product or the
build (verified per build: `ce_inputs: []`).

**The active objective** (roadmap `plans/reference-table-100-roadmap.md`):
100% of the **151 local-only reference-table paths** (143 distinct byte
hashes, frozen manifest `gap_inventory/reference-manifest.json`) must
**load** and **support their intended trainer/cheat behavior** through the
clean-room implementation. "100%" is defined as three separate proofs, all
required:

1. **Load and inspect** — every table is read; every source record and
   game-facing table-level construct is accounted for; UI-only constructs
   are classified separately.
2. **Plan and execute** — every intended actionable record can be built
   and exercised with the right dependency, activation, disable, value,
   resource and UI behavior. A `staged` record counts only after its
   runtime gate is exercised; a named blocked record is honest but does
   **not** count as supported.
3. **Observed effect** — for each original table, representative actions
   and every distinct behavior contract are verified against the intended
   game build or an explicitly equivalent owned target. Static
   compilation and synthetic fixtures alone do not prove the original
   game effect. Windows and Steam Deck acceptance are separate gates.

**Measured end state (0.21, after the RT-5 item B/E merges):**

- Table load: **151/151 paths load, zero load errors** (legacy-binary
  `SuperMeatBoy.CT` loads since RT-3, 2026-10-23).
- Static plan admission: **116,756 supported of 117,809 plan entries**
  (≈99.1%), of which **60,161 staged** behind runtime gates; **1,053
  blocked** with named, catalog-visible reasons (run
  `blocked-catalog-020-rt5-be`, 2026-10-31 — the 0.21 remeasure; the
  denominator grew by the 175 item B code-patch entries, blocked and
  staged unchanged).
- Synthetic feature matrix: **42/42 in-scope feature classes** covered,
  **7,475/7,475 action weight** (run `w4b4-case30-20261020081722Z`) — this
  measures the 30 pinned synthetic corpus tables only, not the original
  corpus.
- Observed game effects (AP-11 campaign): **0 of 6,143** confirmed.
- Runtime acceptance: `runtime_unverified` deliberately kept (Windows
  clean-machine and real Steam Deck/Proton/touch acceptance both still
  pending).

The headline: **static plan admission is at ≈99.1% of the plan-entry
denominator and every table loads**, but under the goal's three-proof
definition the overall 100% reference-table objective is still open —
1,053 named blocked entries, staged runtime behavior not yet exercised in
a live target, and no confirmed original-game effects yet.

## 2. Scope and methodology

### 2.1 The clean-room decision

- CT2Trainer contains **no CE implementation inputs or binaries at all**
  (AGENTS.md, product definition). Builds run exclusively through
  `scripts/Build-Native.ps1`, fully offline with hash-verified inputs from
  `dependencies/`; the in-build CE-content scan verifies `ce_inputs: []`.
- The CE 7.5 source tree at `C:\Users\xboxl\code\cheat-engine-7.5`
  (local-only, never added to git) may be **read** to understand how CE
  handles a behavior (2026-10-13 user decision). It is a **lookup/reference
  source only**: no CE code is copied, derived, or ported — every feature
  is re-implemented clean-room, while public API/format contracts may be
  derived. All other CE implementation sources remain off-limits.
- The original reference tables live in a sibling local-only directory
  (`reference-table-input-do-not-add-to-git`, 151 paths / 143 distinct
  hashes, frozen manifest `gap_inventory/reference-manifest.json`, source
  revision `ea233c26`, generated 2026-10-21). They are strictly read-only
  inputs; distributed releases never contain original game tables. Local
  tooling (converter, tests, corpus analysis) **never executes** original
  table Lua or Auto Assembler; execution is confined to a generated
  trainer attached to its intended target.

### 2.2 Parity scope

The requested parity scope is **trainer/cheat handling and game-facing
effects**. CE's editor and visual UI (scanner, debugger, forms designer,
table editing windows, visual layout) are **outside scope** unless a table
uses a UI API to trigger or calculate a game-facing action — in which case
that API still needs an equivalent behavioral path. A purely decorative UI
call may be classified **no-effect** with a documented scope decision; it
may not be silently ignored when it carries a target action or state
dependency.

### 2.3 Two corpora, two measurements, one effect campaign

The project keeps three measurements strictly separate (roadmap rule;
STATUS.md):

| Measurement | Input | What it proves |
| --- | --- | --- |
| Synthetic feature matrix | 30 pinned synthetic corpus tables in `TableReferences/` (`case-01.ct`…`case-31.ct`, case-to-origin mapping in `TableReferences/README.md`), 6,143 expected actions | The declared feature set is covered end-to-end (compile → plan → engine → byte-exact effect) on owned fixtures. It does **not** establish original-table support or a real game effect. |
| Original-table static catalog | The 151 local-only reference paths, frozen manifest | A static plan-admission profile of the real corpus: which records are supported / staged / blocked and why. Re-measured after each package under run ids `blocked-catalog-*`; local-only evidence (raw artifacts never committed). |
| AP-11 effect campaign | The 30 pinned corpus tables, 6,143 expected actions | Observed game effects on owned/pinned targets. Currently **0/6,143 confirmed**; excluded from the feature metric by definition. |

"Supported" in the static catalog means **plan admission**, not confirmed
effect in a game. A reason count is not an independent feature count; the
catalog is re-measured after each fix, with zero unexplained supported
regressions as the acceptance rule.

### 2.4 CE 7.5 behavior reference probes

Ambiguous CE behaviors were settled by **read-only probes** of the CE 7.5
tree (roadmap section "CE 7.5 behavioral conclusions", probes closed
2026-10-21), each recorded as file:line evidence:

- **Dropdown value overflow: truncation, not refusal** — `TMemoryRecord.SetValue`
  parses the value with `StrToQWordEx` and stores it through the typed
  pointer (`MemoryRecordUnit.pas:3500-3503`, verified this session:
  `vtByte: pb^:=StrToQWordEx(currentValue);` … `vtQword`), so CE truncates
  an out-of-range choice to the record's byte width and never refuses it
  (choice `'314'` on a Byte writes low byte `0x3A` = 58); only unparseable
  strings raise.
- **Module reference without `.exe`** — `TSymhandler.getAddressFromName`
  (`symbolhandler.pas:4985-5103`) tries each token as hex, then exact
  module-name match (extension kept), then Lua symbol callbacks; a bare
  module name without `.exe` fails in CE 7.5 too unless user-configured.
- **IL2CPP `Type:Member` resolution** — zero IL2CPP references in any CE
  7.5 Delphi/Lua table-facing source (IL2CPP code exists only in the
  standalone pipe-server C, an external-process feature with no
  table-facing expression resolution in 7.5); a `Type:Member` atom
  resolves only if a symbol of that exact colon-name is registered.
- Supporting findings: `registeredsymbols.Duplicates := dupIgnore`
  (`autoassembler.pas:338` — verified this session) and
  `allsymbols.Duplicates := dupIgnore` (`:345`); the `label()` identifier
  check `val('$'+name)` rejects only fully-hex names
  (`autoassembler.pas:2577-2578`) with the duplicate-declaration check
  disabled (`:2585-2586`), multiple `name:` definitions still refused
  (`:2599`) and never-defined names refused (`:2603`); `removecomments`
  (`autoassembler.pas:732-798`) is a single-pass state machine without
  nesting support; `usemono` has **0 hits** anywhere in the 7.5 tree
  (newer-CE directive); `BaseAddress` has no built-in Delphi handling
  (user/Lua-defined symbol); CE registers Lua names plus a
  first-character case-flipped variant (`LuaHandler.pas:213-228`).

### 2.5 Governing plan

The active work and completion gates are RT-1…RT-7 in
`plans/reference-table-100-roadmap.md`: RT-1 full-corpus baseline (done
2026-10-21), RT-2 root-cause map for all 2,698 residual blocks (done
2026-10-21), RT-3 load all table formats (done 2026-10-23), RT-4 close
high-volume plan gaps (six packages RT-4.1…RT-4.6, all done, summing to
2,698), RT-5 runtime trainer parity (inventory done 2026-10-23; items
F+G done 2026-10-26, items A+C done 2026-10-28, C2+D done 2026-10-29;
items B+E are the 0.20 cycle), RT-6 full original-table validation
(open), RT-7 release gate (open).

## 3. Per-area behavior comparison

### 3.1 Table load

| Aspect | CE 7.5 | CT2Trainer (0.19) |
| --- | --- | --- |
| Format dispatch | `LoadCT` (`OpenSave.pas:1068-1110`, verified this session): reads the first 11 bytes; `<?XML` → XML document path; `CHEATENGINE` magic → `ConvertCheatTableToXML`; anything else → protected (encrypted) trainer path | `table.py` reads XML; the RT-3 clean-room legacy parser `legacy_ct.py` handles the binary format (2026-10-23). Protected/encrypted tables are out of the corpus and out of scope. |
| Legacy binary format | CE 5.x-era format, 11-byte `CHEATENGINE` magic + version DWORD | True magic is the 11-byte `CHEATENGINE\t` (the 12th byte is the version DWORD's low byte; for version 9 it is a tab, which is why the old 12-byte constant matched only version-9 files by accident). Format versions 6-9 are verified against the reference layout; version > 9 loads with an "assumed unchanged" warning; version < 6 is refused; truncation, corrupt magic and implausible counts carry named `LegacyCTError` refusals. |
| Table-version handling | CE 7.5 writes table version 45 (`OpenSave.pas:24 _CurrentTableVersion=45`, verified this session) | `LOCAL_CE_TABLE_VERSION = 46` (`table.py:37`); the 45 → 46 reference was field-verified in the 0.16.1 field fix (2026-10-21). A newer-than-reference version loads with a warning. |
| Source identity | N/A (in-app) | Record semantics flow through the unchanged, fully tested XML pipeline; the binary's own SHA-256 stays the source identity (`Table.source_sha256`, plan `table_sha256`), matching the frozen reference manifest. |
| Embedded `<Files>` | `TLuafile.createFromXML` (`luafile.pas`, verified this session): `Encoding="Ascii85"` → Base85ToBin → raw-deflate → `ReadDWord` size prefix → read exactly `size` bytes; any other or missing `Encoding` → hex text → HexToBin → raw-deflate → read until EOF (no size prefix) | `embedded_files.py` (RT-5 item A, merge `479977c`, 2026-10-28) implements the same dual-branch codec clean-room, with named decode refusals (empty text, Ascii85 tail/alphabet, odd hex count, truncated/invalid deflate, size-prefix mismatch, 4 MiB per-file bound; 16 MiB per-table total). Table-load decode is fail-closed: one undecodable entry aborts the load with a named `TableError`. |
| `UserdefinedSymbols` | Static symbol section, seeded into the symbol tables | Supported since WP-46 part 1 (static symbol seed) and hardened by RT-4.1 symbol-provider fidelity (keep-first duplicate policy, `lua_symbol_providers.py`); 145 corpus tables carry the section (512 `SymbolEntry`s across 31 tables — inventory §4.7). |
| `<Forms>` (embedded CE UI) | 10 corpus tables embed forms: 7 `CETrainer` Ascii85 `TTrainerForm`s, `IconList` (2), `UDF1` (1) — CE renders them as its own UI | **Outside scope** (purely visual). The table Lua that builds them runs to completion against the WP-56 inert menu/form proxies; the record-toggling actions those forms mediate are covered by the record API. `table.py` surfaces "Embedded CE forms are present; check UI conflicts." |
| `<Structures>` | 16 corpus tables define 1,067 structures / 25,531 elements | **Not interpreted** — no corpus record references the structures (none of the 16 tables has a `CheatEntry` with a `<CustomType>` child); surfaced as the "Table-level sections not interpreted: Structures" warning, plan-inert (inventory §4.8). If a future table references them, structure runtime support becomes an implementation item. |
| `Comments`/`Color`/`LastState`/`RealAddress`/signature sections | Editor annotations, presentation, CE-side persisted state, table-integrity metadata | **No-effect** scope decisions (inventory §4.6/4.10; RT-5 item F ratification pins these byte-exactly): `LastState` is deliberately *not* read back — CT2Trainer keeps its own confirmed-ON persistence and state-lock model, and reading CE's stale state would be a behavior divergence, not a parity win. |
| Table-Lua bootstrap | Table `LuaScript` runs at table load with the full CE Lua host | Bootstrapped at attach on a read-only Lua host (`lua_bootstrap.py`, `lua_host.py`); the API surface is the RT-5 inventory (§3.3); the table-Lua result is pinned in `plan["table_lua"]` and a clean bootstrap is a precondition for the item-D callback dispatch. |

### 3.2 Records

**Value records.** The corpus census (inventory §4.1/§5, 150 XML tables)
covers every value shape: `CheatEntry` 117,648; `Address` 105,205 plus
`Offsets` pointer chains 14,835 (88 tables); value types Byte 44,016
(64 tables), 2 Bytes 17,818, 4 Bytes 14,955, Float 14,374, 8 Bytes 1,866,
String 1,423, Binary 1,347, Array of byte 1,247, Double 105, `Custom` 6
(2 tables); dropdowns `DropDownList` 2,047 (54 tables) +
`DropDownListLink` 19,211 (16 tables).

- **Pointer chains and dynamic bases.** CT2Trainer supports the full
  pointer-chain model plus bounded dynamic bases (WP-38/50), signed
  pointer offsets (WP-14), and — after RT-4.3 — relative-address
  skip-fold staging (O1), pointer-offset expression slots (O3), and the
  runtime-base marker contract on group headings (O9).
- **Staged capabilities.** A supported record whose address depends on a
  provider symbol carries `staged` plan metadata; the engine gates
  read/write/freeze on provider liveness (named fail-closed error while
  inactive, UI pending state with auto-unlock; provider OFF releases
  staged children first). 60,161 of the 116,581 supported entries are
  staged today. A staged entry counts toward the goal only after its
  runtime gate is exercised in a live target.
- **Value semantics (RT-4.4, 2026-10-23).** Matched to the CE 7.5
  `SetValue` behavior verified above: integer writes truncate to the
  record's byte width (choice `'314'` on a Byte writes `0x3A`) instead of
  refusing; bracketed expression choices on simple-numeric records
  compile as `expression: True` and resolve against the runtime symbol
  table at write time (the bracket condition is strict: starts `[`, ends
  `]`, length > 2 — CE `SetValue` 3449-3450 parity, so `[sym]+4` is not
  an expression in either); `ShowAsHex` string records stage a
  byte-array profile; read-only dropdowns with empty or placeholder-only
  choice lists stage as display-only views. Byte-exact engine-level pins
  in `tests/test_native_value_semantics.py`.
- **Custom types.** Static `<CustomTypes>` have a bounded path
  (`custom_types.py`); the corpus's 6 `Custom` records (re2 /
  re2_testicles) use table-Lua-registered types
  (`registerCustomTypeAutoAssembler`) and stay **staged behind the
  AP-08.7 converter/write gate** (O11 class, 6 rows) until that gate
  exists — a deliberate, documented gate, not a silent gap.
- **Group headings.** 12,487 `GroupHeader`s (88 tables) compile to inert
  navigation headings; the `Options` flag classes (13,420 across 112
  tables — `moHideChildren`, `moDeactivateChildrenAsWell`,
  `moRecursiveSetValue`, …) drive activation propagation, bind-activation
  and recursive set in `compiler.py`. Since 0.19, `moAlwaysHideChildren`
  passes through as the `hidden_children` plan marker with row-model
  subtree suppression (South of Midnight staged-options work;
  `tests/test_native_staged_options_ui.py`).
- **Hotkeys.** 247 `Hotkey` entries in 37 tables (361 `Key` bindings; 81
  hotkeys carry a `Value` child for `Set Value`). All six action values in
  the corpus (Toggle 97, Activate 50, Set Value 48, Deactivate 19,
  Increase 18, Decrease 15) are in the supported sets
  (`hotkey_model.py`). Per-record hotkeys are planned (WP-40) with a
  first-wins conflict policy; the runtime bridge is the Windows Win32
  hotkey path — the 0.19 field-fix cycle corrected `HWND_MESSAGE` to -3,
  added explicit `argtypes`/`restype` on all bridge prototypes, and
  guarded `RegisterHotKeyW`/`UnregisterHotKeyW` for stripped user32
  builds (the 0.18 field-test access violation; real-seam regression
  test in `tests/test_native_os_hotkeys.py`).

**Script records — the Auto Assembler engine.** The corpus carries
8,004 `AssemblerScript`s in 147 tables (360 with `Async`); directive
census: `{$lua}` 6,844 (114 tables), `{$asm}` 3,722 (73), `{$STRICT}` 86
(6), `{$try}`/`{$except}` 2 each; `label` 4,545 / `registersymbol` 3,780 /
`unregistersymbol` 2,823 (126/125/124 tables); `alloc` 1,878 (127);
`db` 2,319 / `dw` 53 / `dd` 2,718 / `dq` 668; `nop` 1,627 / `align` 517;
`aobscan` 47 / `aobscanmodule` 1,480 / `aobscanregion` 148; `define` 175;
`assert` 121; `reassemble` 31; `createThread`/`threadWait` 77 (18 tables).

- **Directive coverage.** All of the above are supported by the native AA
  compiler (`aa_program.py` dispatch + `aa_directives.py` contracts) with
  the bundled NASM 3.02 backend; the corpus uses no `{$if}`/`{$else}`/
  `{$process}` (the conditional preprocessor is supported anyway). The
  only corpus directive families not shipped are `createThread`/
  `threadWait` (capability gate, §3.3 item G) and `usemono` (a newer-CE
  directive — 0 hits in the 7.5 tree — reported as out of parity scope,
  4 rows).
- **alloc/dealloc and allocation model.** `alloc`/`globalalloc` compile
  to synthetic private addresses (documented); program cleanup is
  ownership-scoped: a `dealloc`/`unregistersymbol` list may only release
  symbols and allocations owned by the program. CE permits cross-program
  cleanup unconditionally; CT2Trainer keeps the ownership gate with
  actionable diagnostics naming the owning program (O5 class, 31 baseline
  rows; RT-4.5 — documented deliberate divergence).
- **Symbol/provider model.** CE dedupes symbol registration
  (`dupIgnore`, `autoassembler.pas:338/345`) while its AA runtime
  registration is delete-then-add (last-wins). CT2Trainer's documented
  safe narrowing is **keep-first**: a second entry registering an
  already-registered symbol has its duplicate registration shadowed while
  every non-duplicate registration in the same entry still takes effect
  (RT-4.1, 2026-10-22; catalog impact 2,698 → 1,858). Repeated names
  inside one `label()` declaration are tolerated per the CE contract
  (duplicate-declaration check disabled at `autoassembler.pas:2585-2586`;
  multiple `name:` definitions and never-defined names still refused,
  `:2599`/`:2603`). The RT-4.2 runtime provider model (2026-10-27, last
  RT-4 package) completed the picture: Lua-runtime-registered symbol
  providers resolve staged (286 rows), Windows API-export atoms
  (`GetAsyncKeyState`, `FindWindowA`) resolve at link time against the
  target export table with the `api_exports` plan marker (12 rows), and a
  keep-first scope fallback covers mixed duplicate-provider programs.
  RT-4.3 (2026-10-26) closed the address-expression and identifier
  dialect: relative-address skip-fold (195 rows), pointer-offset
  expression slots (51), quoted module+offset and `Type:Member` trailing
  atoms (38), digit-leading and dot-bearing identifiers per the CE
  `label()` contract, runtime-base staging (8), directive-aware string
  data bytes `db`/`dw`/`dd`/`dq` (5).
- **Byte patches.** The 0.15 prefix-cut field fix (Great Circle) added
  link-time proof of `db`-style patches over live target bytes with
  re-verification at stage time — the byte-patch plan path is
  evidence-backed, not assumed.
- **Code patches (`CheatCodes`).** 22 corpus tables carry 175
  `CodeEntry` records (before/actual/after byte sequences; 124
  `AddressString` module+offset targets) — CE presents these as
  standalone activatable patches with verify-before/apply-actual/
  restore-after. CT2Trainer currently does **not** interpret the section
  (named warning "Table-level sections not interpreted: CheatCodes").
  **This is RT-5 item B: the code-patch plan path is being implemented in
  the 0.20 release cycle in parallel with this document — final numbers
  pending the 0.20 catalog remeasure (≈+175 plan entries expected).**

### 3.3 Lua surface (RT-5)

The RT-5 inventory (`documentation/rt5-api-inventory.md`, 2026-10-23)
catalogued every CE Lua API used by the 49 corpus table `LuaScript`s plus
the 17 embedded `.lua` files: **394 distinct call names**, cross-classified
against the CE 7.5 registration surface (1,008 distinct `lua_register`
global names + 542 class-method names across the tree; authoritative
`LuaHandler.pas` plus `LuaStrings.pas`, `LuaStringlist.pas`,
`LuaTableFile.pas`, `LuaTimer.pas`): **61 CE globals, 36 CE object
methods, 28 stdlib/builtins, 269 table-local or obfuscated names**.

- **20 CE globals already hosted** (WP-era work): `createMenuItem` /
  `getMainForm` (WP-56 inert menu/form proxies), `shellExecute` (safe
  no-op + table-load warning), `showMessage` (whitelisted, logged),
  `openProcess` (truthy no-op with identity verify), `readInteger` /
  `writeInteger` / `readPointer` / `writeQword` / `getAddress` /
  `getAddressSafe` / `getModuleSize` (whitelisted), `getLuaEngine`,
  `getAddressList`, `AOBScan`, `createFoundList`, `createMemScan`,
  `registerSymbol` / `unregisterSymbol`, `sleep` (owned scheduler). The
  `mono_*` managed-resolution APIs are whitelisted but unused by the
  corpus. Undefined CE globals get the exact named refusal
  `Unsupported CE Lua API: <name>` — fail-closed, never a silent no-op.
- **Item A — embedded files + local string access (done 2026-10-28,
  merge `479977c`):** `findTableFile` / `readStringLocal` /
  `stringstream.*` / stringlist `Text` surface, built on the dual-branch
  embedded-file codec (§3.1). Closes the table-Lua bootstrap gap for
  Octopath2, P5Strikers (+ copy) and RiftApart (the 4 tables whose
  table Lua loads embedded helpers; the remaining embedded files in
  Cronos, DeathStrandingDC, Resonance and SC2 are no-effect UI assets).
  +53 tests, zero catalog delta (`blocked-catalog-rt5a-main`).
- **Item C — bounded process-info family (done 2026-10-28, commit
  `0167825`):** 11 APIs under the clean-room single-target model —
  `getProcessIDFromProcessName`, `getProcessList` (single-entry map),
  `getAutoAttachList` (inert singleton), `getOpenedProcessID`,
  `getSettings`, `integerToUserData`, `targetIs64Bit`, `enumModules`,
  `disassemble` (bounded iced-x86 exposure), `stringlist_add`,
  `getCEVersion`. 44 of the 151 tables reference at least one of them.
  +23 tests, zero catalog delta (`blocked-catalog-rt5c-main`).
- **Item C2 — dynamic addresslist records + custom AA directives (done
  2026-10-29, merge `dde9f04`):** `createMemoryRecord` creates
  engine-owned session journal entries (synthetic IDs ≥ 2**31, never
  persisted, cleared on target exit, bounded at 4096) with the full CE
  `MemoryRecord` runtime surface (Description/Type/Address/Script/
  Parent/Child/Offset/Value, `vtByte`..`vtDouble`); journal and
  plan-record `OnActivate`/`OnDeactivate` callbacks; addresslist lookups
  (`getMemoryRecord` / `getMemoryRecordByID` / `getMemoryRecordByDescription`);
  `registerAutoAssemblerCommand` / `unregisterAutoAssemblerCommand` for
  table-scope custom AA directives (built-in names refused). `getCEVersion`
  superseded from the string pin to the number **7.5** (CE 7.5
  LuaHandler pushnumber parity). +27 tests, zero catalog delta
  (`blocked-catalog-rt5c2-main`).
- **Item D — table event callbacks (done 2026-10-29, merge `9294bb8`):**
  CE dispatches `onTableLoad(before)` at load start/end
  (`OpenSave.pas:337` `[true]` / `:998` `[false]`, verified this session)
  and `onOpenProcess(processId)` on attach (`ProcessHandlerUnit.pas:193`,
  verified this session). CT2Trainer fires both in CE sequence on the
  table-scope host after a clean table-Lua bootstrap: `onOpenProcess`
  with the attached target PID, then `onTableLoad(false)`. Documented
  bounded deviation: the once-per-attach bootstrap has no before-load
  phase, so `onTableLoad` only ever sees `false`. Each callback runs in a
  pcall-wrapped chunk with literal argument injection; a throwing
  callback is contained without touching `plan["table_lua"]`
  (byte-identity pinned); dispatch is idempotent per confirmed attach and
  re-fires on re-attach. The corpus dependency this closes: the
  FearlessRev tables (Resonance, Sinking City 2) set `myGame =
  getProcessList()[processId]` in `onOpenProcess`, and their table-scan
  Lua then uses `getAddress(myGame)` — a game-facing chain. +9 tests,
  zero catalog delta (`blocked-catalog-rt5d-main`).
- **Item E — `messageDialog` decision:** 69 calls across 31 tables;
  currently a named refusal + load-time review warning. The decision
  (safe no-op with review flag vs. refusal) is part of the **0.20 cycle —
  final decision and numbers pending**.
- **Item F — no-effect register ratification (done 2026-10-26, merge
  `966fccd`):** the inventory's section-8 register (26 CE UI globals +
  object methods, Forms/IconList/UDF1, Signatures, `LastState`,
  `ActivateSound`/`DeactivateSound`, embedded images) is now pinned as a
  byte-stable contract in `tests/test_native_rt5_no_effect_register.py`
  (+22 tests) — every pure-UI API keeps its exact named refusal with zero
  target side effects.
- **Item G — `createThread`/`threadWait` gate decision (done 2026-10-26,
  merge `2de9c0e`):** option (2) recorded — the capability gate stays and
  no thread backend ships this milestone; a bounded owned-thread backend
  awaits a root design review (thread lifecycle, debug-event ownership,
  join semantics, exact disable teardown, journal receipt). The
  five-stage fail-closed chain is pinned byte-stable in
  `tests/test_native_rt5_thread_gate.py` (+17 tests). Census re-derived:
  2 O22 catalog rows (Witcher3 4.02HF1_G25v2 + 4.03_G25v2, id 192,
  "Call Function") plus 77 first-word `createThread` usages across 18
  tables (26 AA directive lines in 8 tables, gate-governed; 51
  Lua-context lines in 11 tables — the `lua_host` cooperative-worker
  family, not O22-gated); zero first-word `threadWait` lines.

### 3.4 Runtime model

| Aspect | CE 7.5 | CT2Trainer (0.19) |
| --- | --- | --- |
| Process model | Multi-process: open/switch processes, auto-attach lists, per-process state | **Single pinned target** per plan (exact EXE name binding at compile time; `openProcess` is a truthy no-op with identity verify; item-C APIs answer only from the attached target). Rationale: private own use, one table per game; documented bounded narrowing, not a gap. |
| Attach & recovery | Debugger attach, re-attach on crash, symbol re-resolution | Attach with a bounded module-snapshot retry: 8-attempt exponential backoff on Win32 codes {1116, 24, 119}, architecture-aware native-only fallback flag (0.16.3 field fix); recovery assessment validates the hook-journal fields (`captured_placeholders`, `value_data_ranges`) before startup. |
| State persistence | CE's own per-record `LastState` / activation flags | Own confirmed-ON wish model: only confirmed ON-switches persist; a failed enable stays visibly inactive and is not repeated; stale `state.lock` self-repair with actionable refusal (0.16 field-fix cycle); atexit session/lock release on a provably gone target. |
| Undo / byte-exact restore | Memory restoration from recorded original bytes | WP-47/55/57 hook journaling: byte-exact undo/restore of patched regions, with journal fields validated by the recovery schema; the 0.16.2/0.16.3 field tests proved the journal-field acceptance chain on Sinking City 2. |
| Clock binding / speed control | Live `SetSpeed` clock binding on the target | Bounded clock contracts with owned-fixture tests only; no live managed/speed path is claimed (static IL2CPP probe is read-only; `mono_*` Lua APIs whitelisted but unused by the corpus). |
| Hotkey bridge | In-process key handling | Win32 `RegisterHotKeyW` bridge on `HWND_MESSAGE` (corrected to -3 in 0.19), explicit argtypes/restype, guarded registration for stripped user32 builds; `run_trainer` logs `hotkey-bridge-started`/`-failed`. |
| Crash observability | N/A (host app) | 0.16.4 `arm_crash_reporting()`: one-time process-wide `excepthook` / `threading.excepthook` / `faulthandler` into the opt-in debug log; `TrainerWindow.poll` fails closed instead of letting an exception kill the windowed process (0.16.3 field finding: silent mid-restore death, zero follow-up events). |
| Value-read observability | N/A | 0.19: `read_value` logs `value-read-failed` per identifier per cause (dedup, re-raise) — the 0.18 field finding (staged pointer-chain reads failing silently with a blank "unavailable") is now diagnosable. |
| Lua execution | Full CE Lua host inside the trainer | Real Lua 5.3 via Lupa 2.8 (MIT), independently authored host adapters (`lua_host.py`, `lua_bootstrap.py`, `lua_activation.py`); allowlist-based admission, fail-closed named refusals, bounded registries; `{$lua}` sections route through the same host. |

### 3.5 UI scope

- **CE 7.5** ships a full editor application: memory scanner, debugger,
  code analyzer, table editor with forms designer, structure forms,
  embedded CETrainer forms, menus, dialogs.
- **CT2Trainer ships a trainer, not the editor**: the row-based trainer
  UI (toggle / value / freeze per record, staged-pending tap guard,
  `hidden_children` subtree suppression), the **Scripts filter view**
  (every script record — blocked and unselected included — with its
  reason; 0.17), the **row context menu** (right-click / long-press:
  script preview of the executed Auto Assembler / Lua source, copy-script,
  plain-language entry assessment, unchanged Info dialog; 0.17) and the
  **row-details window** (0.18: raw script source + plain-language
  assessment + the concrete actions the trainer performs per entry).
  The 0.19 `describe` CLI subcommand exposes the same raw-source +
  assessment + actions view from the command line.
- **Declared out of scope:** CE's visual UI and editor features. Table
  Lua that builds CE forms runs against inert proxies (WP-56); the
  record-toggling actions those forms mediate are already covered by the
  record API, so no game-facing effect is lost by not rendering the form.
  Purely decorative UI calls (e.g. `GetAddressList` dark-mode usage in
  AtomicHeart, `playSound`) are documented no-effect decisions pinned by
  the item-F register.

## 4. Measured end state vs the 100% goal

Per the project rule, three measurements are kept strictly separate and
none may be reported as the result of another (STATUS.md, roadmap):

1. **Synthetic feature matrix** — the 30 pinned corpus tables in
   `TableReferences/`; proves the declared feature set end-to-end on
   owned fixtures, **not** original-table support.
2. **Original-table static catalog** — the 151 local-only reference
   paths (frozen manifest); proves static plan admission with named
   block reasons, **not** observed effect.
3. **AP-11 effect campaign** — observed game effects on owned/pinned
   targets; the only proof that counts toward "observed effect"
   (roadmap proof plane 3).

### 4.1 Original-table catalog — the baseline chain

The local-only static catalog (raw artifacts never committed) has been
remeasured after every package; every run is named, and the frozen
manifest (`gap_inventory/reference-manifest.json`, 151 paths / 143
distinct hashes, source revision `ea233c26`) and process bindings are
unchanged across the chain:

| Step | Date | Run id | Blocked | Plan entries | Staged | Table load |
| --- | --- | --- | --- | --- | --- | --- |
| Wave-4 baseline (RT-1 rebaseline reproduces per table) | 2026-10-20/21 | `w4b4-case30-20261020081722Z` → `blocked-catalog-rt1` | 2,698 | 117,624 | 58,950 | 150/151 (1 legacy-binary error) |
| RT-4.1 symbol provider fidelity | 2026-10-22 | `blocked-catalog-rt41` | 1,858 | 117,624 | 59,642 | 150/151 |
| RT-3 legacy-binary CT loader | 2026-10-23 | `blocked-catalog-rt3` | 1,858 | 117,634 | 59,642 | **151/151** |
| RT-4.4 value semantics | 2026-10-23 | `blocked-catalog-rt44` | 1,807 | 117,634 | 59,683 | 151/151 |
| RT-4.6 input legacy & authoring gaps | 2026-10-24 | `blocked-catalog-rt46` | 1,778 | 117,634 | 59,709 | 151/151 |
| RT-4.5 AA directive & script coverage | 2026-10-24 | `blocked-catalog-rt45main` | 1,743 | 117,634 | 59,735 | 151/151 |
| RT-4.3 address expression & identifier dialect | 2026-10-26 | `blocked-catalog-rt43-main` | 1,351 | 117,634 | 59,868 | 151/151 |
| RT-4.2 runtime provider model (RT-4 complete) | 2026-10-27 | `blocked-catalog-rt42-main` | **1,053** | 117,634 | 60,161 † | 151/151 |
| RT-5 items A / C / C2 / D (zero delta at each step) | 2026-10-28/29 | `blocked-catalog-rt5a-main` / `-rt5c-main` / `-rt5c2-main` / `-rt5d-main` | 1,053 | 117,634 | 60,161 | 151/151 |
| 0.19 field-fix cycle (zero delta vs item D) | 2026-10-30 | `blocked-catalog-019-field` | **1,053** | 117,634 | 60,161 | 151/151 |
| 0.20/0.20.1 branding icons (zero delta vs 0.19 field) | 2026-10-30/31 | `blocked-catalog-020-icons` | 1,053 | 117,634 | 60,161 | 151/151 |
| RT-5 item B code-patch path (item E zero delta, run `blocked-catalog-rt5e-iteme`) | 2026-10-31 | `blocked-catalog-020-rt5-be` | **1,053** | **117,809** | 60,161 | 151/151 |

† The item-A remeasure (`blocked-catalog-rt5a-main`) records **zero
delta** against the RT-4.2 state, including the 60,161 staged entries
and 116,581 supported; every later run repeats the same zero-delta
statement. The item B remeasure (`blocked-catalog-020-rt5-be`) adds
exactly the expected 175 plan entries — all supported `code_patch`
records, zero newly blocked, zero reason changes — confirming the
inventory census.

**Current measured state** (run `blocked-catalog-020-rt5-be`,
2026-10-31): **151/151 table paths load with zero load errors**;
**117,809 plan entries**, of which **116,756 supported (≈99.1%)** —
including **60,161 staged** behind runtime gates — and **1,053 blocked**,
each with a named, catalog-visible reason.

### 4.2 Top blocked reasons

The baseline decomposition (2,698 rows) is the RT-2 root-cause map
(roadmap §RT-2; lane final report 2026-10-21, authoritative record):
**1,931 symbol-provider rows** — R1 duplicate-provider cascades 624, R2
wildcard-cascade 3, R3 hidden provider entries 963, R4 Lua-runtime
symbols 110, R5 no-registration-anywhere 91, R6 legacy/user-expected
128, R7 API-export atoms 12 — and **767 direct rows in 27 classes** —
O1 relative-address skip 331, O2 duplicate-provider direct 186, O3
pointer-offset hex literals 53, O4 trailing tokens 43, O5 cleanup
ownership 31, O6/O7/O8/O26 dropdown semantics 30/15/13/1, O9 no
address-bearing ancestor 10, O10 identifier strictness 8, O11
custom-type gate 6, O12 `aobscanregion` 5, O13 indirect data 5, O14
inline `{$lua}`/`{$c}` 4, O15 `usemono` 4, O16 dup label 4, O17
wildcard direct 3, O18 alloc sub-errors 3, O19/O20/O21 global-init
profiles 2/2/2, O22 `createThread` 2, O23–O27 one row each. Every class
carries a testable contract; the classification legend separates (a)
real missing CE semantics, (b) conservative false positives, (c)
deliberate CT2Trainer policy, (d) authoring gaps / inputs CE 7.5 also
fails.

The six RT-4 packages then cleared the fixable classes in order
(remeasures in §4.1), with zero newly blocked rows at every step and
zero unexplained supported regressions. The **current 1,053 residual**
composes, per the documented class outcomes, of:

- **Authoring / user-configuration rows (dominant residual)** — R5
  (91 at baseline: no registration anywhere in the table; CE resolves
  these only via user-side symbols, cross-table loading, or dynamic Lua)
  and R6 (128 at baseline: legacy built-ins such as `BaseAddress`,
  module names without `.exe`, register-like tokens). RT-4.6 cleared
  the mechanically provable subset (29 rows) and turned the rest into
  the actionable per-symbol report (`Required symbol '<S>' is not
  registered anywhere in this table … Import it as a user symbol with
  its target address, or add a record that registers it`); the
  user-symbol import path (`--user-symbols`, `load_user_symbols`, plan
  field `user_symbols`) covers the user-configured subset.
- **Documented policy divergences** — the O5 cross-program cleanup rows
  keep the ownership-gate refusal with actionable diagnostics naming
  the owning program (CE permits cross-program cleanup; deliberate
  safety narrowing).
- **Deliberate capability gates** — O11 `Custom` vartype (6 rows,
  AP-08.7 converter/write gate), O15 `usemono` (4 rows, newer-CE
  directive with 0 hits in the 7.5 tree), O22
  `createThread`/`threadWait` (2 rows, item-G gate).
- **Input-legacy rows CE 7.5 also fails** — e.g. O25 the unterminated
  `{` block comment (CE's single-pass `removecomments` fails
  identically, `autoassembler.pas:732-798`) and O23 the `$proces`
  quoted-atom typo (authoring gap; the refusal now names the offending
  token).
- **Residual hidden-provider rows** whose roots span packages (e.g. the
  DS2 `myPtr` family, 44 rows at baseline, with multiple per-entry
  provider block reasons — any single root fix resolves those rows, so
  per-class deltas are not additive).

The exact per-reason composition of the current 1,053 lives in the
local-only catalog artifacts (named per run, never committed); the
category view above is the documented one.

### 4.3 Synthetic feature matrix

Run `w4b4-case30-20261020081722Z` (`gap_inventory/feature-coverage.json`,
committed): **42 of 42 in-scope feature classes covered** (46 classes
total, 4 excluded as AP-11-only), **7,475/7,475 action weight** over the
30 pinned synthetic tables with 6,143 expected actions (6,145 records
minus 2 navigation entries; 4 group-toggle actions tracked separately).
`consistency.all_ok: true` — including `confirmed_game_effect_zero`,
the pinned table set, the category-count sums and the gap-label
contracts. This metric measures the synthetic corpus end-to-end only; it
does **not** establish original-table support or any real game effect.

### 4.4 AP-11 effect campaign

**0 of 6,143 confirmed game effects** (`gap_inventory/gap-report.json`,
run `w4b4-case30-20261020081722Z`: `confirmed_game_effect_actions: 0`,
`confirmed_percent: 0.0`). The campaign is a separate end goal,
excluded from the feature metric by definition; it is roadmap proof
plane 3.

### 4.5 Build and suite state (0.21)

Latest verified build: **0.20.1**,
`native-20261031T104114Z-d64ae4c2`, cut from `main` @ `080128c`
(2026-10-31): in-build suite **3,854 OK / 26 expected skips**,
`ce_inputs: []`, `runtime_unverified` deliberately kept per gate
(source ZIP `CT2Trainer-0.20.1-source.zip` sha256 `d6ced6ee…`, portable
ZIP `CT2Trainer-0.20.1-windows-portable.zip` sha256 `c8f022b1…`).
Superseded 0.20 build `native-20261030T184820Z-b9d6dc07` (2026-10-30,
branding icons, in-build 3,854/26, zero catalog delta
`blocked-catalog-020-icons`). The 0.21 build from this content set (RT-5
items B + E, this document) records its in-build suite and archive
hashes in the release docs (`AGENTS.md`,
`documentation/native-progress.md`).

## 5. Remaining gaps and documented bounded deviations

Each entry below is a recorded scope decision with its rationale and
evidence; none of them silently diverges from CE 7.5. The two RT-5
decisions open at drafting (item B code-patch path, item E
`messageDialog`) landed in the 0.21 cycle; item E is row 3 below, item
B in inventory section 4.9 and §4.1 above.

| # | Deviation / gap | CE 7.5 behavior | CT2Trainer behavior | Rationale and evidence |
| --- | --- | --- | --- | --- |
| 1 | **Single-target process model** | Multi-process: open/switch processes, auto-attach lists, per-process state | One pinned target per plan (exact EXE binding at compile time); item-C APIs answer only from the attached target; `openProcess` is a truthy no-op with identity verify; `getProcessList` single-entry map; `getAutoAttachList` inert per-scope singleton | Private own use, one table per game; a multi-process model would widen the API and security surface with no corpus demand. Evidence: roadmap clean-room boundary; item C update (commit `0167825`). |
| 2 | **No before-load `onTableLoad` phase** | `onTableLoad(true)` before parsing (`OpenSave.pas:337`, verified this session) and `onTableLoad(false)` after (`:998`, verified) | Only the after-load dispatch fires (`onTableLoad(false)`), in CE sequence with `onOpenProcess` (`ProcessHandlerUnit.pas:193`, verified), after a clean table-Lua bootstrap | The once-per-attach bootstrap has no before-load phase; the corpus callbacks (Resonance, Sinking City 2) only use the after-load state. Evidence: item D (merge `9294bb8`); `tests/test_native_rt5_table_callbacks.py`. |
| 3 | **`messageDialog` — safe logged no-op (item E, 0.21)** | User-facing dialog (69 calls, 31 tables) | Safe logged no-op returning 0 (mbOK, truthy in Lua): CE 7.5 argument shapes (message / title+message / dialogtype / buttons), nil argument tolerance (corpus table Lua passes undefined button constants as nil), `message-dialog` debug event, both spellings, record + table scope | Purely UI presentation; the safe no-op preserves table flow for informational dialogs, while a refusal would break table Lua that continues after the call. Evidence: item E (merge `b8bb4ee`; `tests/test_native_rt5_message_dialog.py` +22); zero catalog delta (`blocked-catalog-rt5e-iteme`). |
| 4 | **`shellExecute` safe no-op** | Executes an external command/URL (31 tables) | Safe no-op + table-load warning split per API (WP-56) | External process launch is outside the trainer contract and a safety risk in a game-process context; no corpus table depends on the launch result for a game-facing action. Evidence: WP-56 (0.16 content); 0.16.1 accurate-warning fix. |
| 5 | **`createThread`/`threadWait` capability gate** | AA thread directives spawn target threads | Five-stage fail-closed gate (tokenizer → one-shot grammar → staged-runtime gate → converter composite reason → engine `NativeRuntimeError` with zero allocation/symbol/write side effects); no thread backend ships this milestone | Item-G option (2): a bounded owned-thread backend requires a root design review first (thread lifecycle, debug-event ownership, join semantics, exact disable teardown, journal receipt). Evidence: item G (merge `2de9c0e`); `tests/test_native_rt5_thread_gate.py` +17; census 2 O22 rows + 77 usages in 18 tables. |
| 6 | **`Structures` sections not interpreted** | 16 tables define 1,067 structures / 25,531 elements; CE renders structure forms | "Table-level sections not interpreted: Structures" warning; plan-inert (byte-exact differential vs a construct-free control) | No corpus record references the structures (none of the 16 tables has a `CheatEntry` with a `<CustomType>` child) — unreferenced editor metadata here; if a future table references them, structure runtime support becomes an implementation item. Evidence: inventory §4.8; item F register pin. **`Forms` (10 tables) is the same decision class** — outside scope, table Lua runs against the WP-56 inert proxies. |
| 7 | **Staged-capability gate** | CE resolves provider symbols live at runtime | Supported records with provider-dependent addresses carry `staged` plan metadata; the engine gates read/write/freeze on provider liveness (named fail-closed error while inactive, UI pending state with auto-unlock) | The static compiler cannot resolve runtime-registered symbols; the gate is honest about the dependency and fails closed. 60,161 staged entries await live exercise. Evidence: WP-14 staged capabilities; roadmap proof plane 2 (a staged record counts only after its runtime gate is exercised). |
| 8 | **`getCEVersion` pinned to 7.5** | Returns the running CE version as a number | Returns the number **7.5** (item C2 supersedes the item-C string pin '7.5') | The product implements the CE 7.5 surface; tables use the value as a CE-version gate and the corpus gates numerically (string usages coerce through Lua). Evidence: item C (commit `0167825`) + item C2 (merge `dde9f04`). |
| 9 | **`readStringLocal` maxsize / NUL semantics** | Default maxsize 50 bytes; NUL truncation on read | Omitted/negative maxsize returns the full content; no NUL truncation | The content is the embedded asset itself — a 50-byte default would break the corpus' full-file loads, and NUL truncation would corrupt binary assets. Documented clean-room deviations, both corpus-compatible. Evidence: item A update (merge `479977c`). |
| 10 | **Keep-first duplicate-provider policy** | `dupIgnore` dedupe of the registration list (`autoassembler.pas:338/345`, verified this session) + delete-then-add runtime registration (last-wins, `autoassembler.pas:4164-4208`) | Keep-first: the first supported registration wins; a later duplicate registration is shadowed while the entry's other registrations still take effect | CE's last-wins can let a later script silently steal a symbol the plan already committed to; keep-first is the documented safe narrowing with the same observable result for the corpus. Evidence: RT-4.1 (2026-10-22); `lua_symbol_providers.py`; catalog 2,698 → 1,858. |
| 11 | **Cross-program cleanup refusal** | `dealloc` / cleanup may release symbols/allocs owned by other programs unconditionally | Ownership gate: a program's cleanup may only release its own symbols/allocs; foreign references are reported with the owning program | Cross-program release can free memory another record still uses — a silent corruption path; the gate is a deliberate safety narrowing with named, catalog-visible reasons. Evidence: O5 class (31 baseline rows); RT-4.5 (2026-10-24). |
| 12 | **`usemono()` out of parity scope** | N/A — 0 hits in the CE 7.5 tree (newer-CE directive) | Named refusal: reported as targeting a CE newer than 7.5 | Parity is defined against CE 7.5; a directive CE 7.5 cannot execute is out of scope by definition. Evidence: O15 class (4 rows, ForgottonAnne + 小猫咪); RT-4.5; CE tree census (0 hits). |
| 13 | **O11 custom-type gate (RE2 family)** | CE resolves Lua-registered custom types at runtime | The 6 `Custom`-vartype records (re2 / re2_testicles) stay staged behind the AP-08.7 converter/write gate (`CustomTypeAbort` payload) | Runtime-only type definitions need a converter/write gate before they can be exercised safely; a deliberate documented gate, not a silent gap. Evidence: inventory §4.13; RT-4.4 update (gate unchanged by design). |
| 14 | **Process-info answer-shape deviations** | `getProcessIDFromProcessName` answers nil for a non-matching name; `enumModules` reports the OS `PathToFile`; `disassemble` lines in CE's uppercase style | `0` for a non-matching name (corpus tolerates both shapes); `PathToFile` falls back to the EXE name when the backend reports no image path; disassemble lines in pinned iced Intel syntax (lowercase) | Single-target model: the APIs answer only from the attached target; the iced syntax is the pinned decoder's canonical output. All three are documented per-API deviations. Evidence: item C update (commit `0167825`). |
| 15 | **`LastState` deliberately not read back** | CE persists last values/addresses per record (2,701 entries, 42 tables) | Own state model (confirmed-ON persistence, state lock); the attribute is a no-effect decision | Reading CE's stale state back would be a behavior divergence (stale addresses/values from a different CE session); the product's own persistence is the source of truth. Evidence: inventory §4.6; item F register pin. |
| 16 | **`runtime_unverified`** | N/A | Both final acceptance gates still open: the Windows clean-machine protocol and the real Steam Deck under Proton with touch operation | 0.9.0-rc2 was the only user-tested baseline (machine without CE or Python); later field tests (Sinking City 2, South of Midnight) ran on a machine with the toolchain present. `runtime_unverified` stays set until both RT-6 protocols pass with recorded build hashes. Evidence: `native-verification.md` §1; STATUS.md final-platforms row. |
| 17 | **AP-11 effects unconfirmed** | N/A | 0 of 6,143 observed game effects | Proof plane 3 (observed effect) is separate from static admission by design; RT-6 runtime observation is the verification path. Evidence: `gap_inventory/gap-report.json` denominator; roadmap RT-6. |

**Closed during drafting:** RT-5 item B — the `CheatCodes` code-patch
plan path (22 tables / 175 entries; the section was the named warning
"Table-level sections not interpreted: CheatCodes") landed in the 0.21
cycle with exactly +175 supported plan entries and zero newly blocked
rows (run `blocked-catalog-020-rt5-be`) — and item E
(`messageDialog`, row 3 above), a zero-catalog-delta runtime host
behavior. RT-5 is complete; the remaining work is RT-6 validation and
the RT-7 release gate.

## 6. Conclusion

**What the evidence proves (0.21, after the RT-5 item B/E merges):**

- The product is a genuine clean-room implementation: every build passes
  the offline build with `ce_inputs: []`, and the CE 7.5 tree was used
  only as a read-only behavior reference (probes closed 2026-10-21,
  file:line evidence in §2.4).
- **All 151 reference-table paths load** — both the XML format and the
  CE 5.x-era legacy binary format (`SuperMeatBoy.CT` since RT-3) — with
  zero load errors and source identity preserved (manifest SHA-256s).
- **Static plan admission covers 116,756 of 117,809 plan entries**
  (≈99.1%), every blocked entry carrying a named, catalog-visible
  reason; the baseline chain from 2,698 blocked to 1,053 was driven by
  six re-measured RT-4 packages with zero newly blocked rows at every
  step and zero unexplained supported regressions, the RT-5 items
  A/C/C2/D/E added runtime host behavior at zero catalog delta each,
  and item B added exactly its 175 code-patch entries as supported
  records with zero newly blocked rows.
- The **42/42 in-scope feature matrix** (7,475/7,475 action weight)
  proves the declared feature set end-to-end on the 30 pinned synthetic
  tables with byte-exact engine-level evidence.
- The CE-behavior conclusions (truncating `SetValue`, `dupIgnore`
  registration, the `label()` identifier contract, single-pass comment
  stripping, `usemono` absent, the `onTableLoad(true/false)` +
  `onOpenProcess` dispatch sequence, the dual-branch embedded-file
  codec) are each pinned to CE 7.5 file:line locations, and
  CT2Trainer's corresponding semantics are pinned by dedicated test
  modules (3,902-test main suite as of the 0.21 content commit).

**What remains open:**

1. **1,053 named blocked plan entries** — the residual authoring /
   user-configuration rows, the documented policy divergences (cleanup
   ownership, keep-first provider policy), and the deliberate
   capability gates (O11 custom types, O15 usemono, O22 threads); the
   exact per-reason composition is in the local-only catalog artifacts.
2. **Staged runtime proof** — 60,161 staged entries count toward the
   goal only after their runtime gates are exercised in live targets
   (RT-6).
3. **AP-11 observed effects** — 0/6,143; the separate end goal (this
   includes the 175 code-patch entries' real-game effect).
4. **Final platform acceptance** — Windows clean-machine and real Steam
   Deck under Proton with touch, both still `runtime_unverified`.

**Verification path to closing the 100% objective** (roadmap RT-6/RT-7):

1. Cut the 0.21 build through `scripts/Build-Native.ps1` and record
   its id, in-build suite and archive hashes in the tracking docs
   (release cycle; the build record in §4.5 is completed by that
   change).
2. RT-6 plan inspection: split the 151 paths into chunks, one lane per
   chunk, each producing the per-path plan-inspection result plus an
   honest skip record for every target it cannot access (pinned game
   build unavailable, no live runtime observation possible).
3. RT-6 runtime observation: targeted observations against pinned game
   builds (activation, values, freeze, re-attach, disable/undo,
   one-shot), then the Windows clean-machine protocol and the
   Deck/Proton/touch protocol, each recorded with exact build hashes
   before any status raise.
4. RT-7 release gate (single-threaded at root): rebuild only through
   `scripts/Build-Native.ps1`, full suite + source/frozen parity,
   `ce_inputs: []`, archive hashes and provenance, updated tracking and
   verification records — then the 100% claim, with the three proof
   planes each independently satisfied.

Until each of those is green, the honest summary is: **every table
loads, static plan admission is at ≈99.1% with every residual named,
the synthetic feature set is fully proven, and the observed-effect
plane is the remaining work.**

## 7. Sources and citations

**Repository artifacts (main, 0.21 cycle, 2026-10-31):**

- `STATUS.md` — measured end state, superseded-build chain, goal
  definition (2026-10-30).
- `plans/reference-table-100-roadmap.md` — RT-1…RT-7 and the three
  proof planes; the RT-2 root-cause map (2,698 = 1,931 + 767 with
  per-class counts and testable contracts); the RT-4 package split;
  the CE 7.5 behavioral conclusions; the per-item RT-5 landing
  updates with remeasure run ids.
- `plans/TRACKING.md` — current measurement snapshot (catalog chain,
  release records, AP-11 state).
- `documentation/ce-feature-parity-assessment.md` — the capability map
  and the reproducible general-assessment method (2026-10-20).
- `documentation/rt5-api-inventory.md` — the RT-5 census: table-level
  construct counts (§4), value types and address shapes (§5), AA
  directive inventory (§6), the 394-name Lua API split (61 CE globals
  / 36 object methods / 28 stdlib / 269 table-local) and the
  hosted / named-refusal / no-effect registers (§7–§8), the
  implementation queue (§9).
- `documentation/native-progress.md`, `native-runtime.md`,
  `native-verification.md` — build/suite baselines, component pins,
  verification gates and the `runtime_unverified` state.
- `documentation/subagent-lane-rules.md` — the lane mechanism this
  document was produced under (report format §11).
- `gap_inventory/feature-coverage.json` (run
  `w4b4-case30-20261020081722Z`) — 42/42, 7,475/7,475, consistency
  `all_ok: true`; `gap_inventory/gap-report.json` (same run) — 6,143
  expected actions, 0 confirmed game effects;
  `gap_inventory/reference-manifest.json` — 151 paths / 143 distinct
  hashes, source revision `ea233c26`, frozen 2026-10-21.
- `src/ct2trainer/table.py` (version handling,
  `LOCAL_CE_TABLE_VERSION = 46`, embedded-Files parsing),
  `src/ct2trainer/legacy_ct.py` (RT-3 binary parser),
  `src/ct2trainer/native/embedded_files.py` (RT-5 item A codec),
  `src/ct2trainer/native/lua_host.py` (hosted Lua surface),
  `src/ct2trainer/native/lua_bootstrap.py` / `lua_activation.py`
  (table-Lua lifecycle and callbacks),
  `src/ct2trainer/native/aa_program.py` / `aa_directives.py` (AA
  compiler), `src/ct2trainer/native/lua_symbol_providers.py` (RT-4.1
  keep-first policy), `hotkey_model.py`, `custom_types.py` —
  implementation locations cited per area in §3.

**CE 7.5 local source tree (`C:\Users\xboxl\code\cheat-engine-7.5`,
read-only; file:line verified this session unless noted):**

- `Cheat Engine\OpenSave.pas:24` — `_CurrentTableVersion=45`;
  `:1068-1110` — `LoadCT` format dispatch (11-byte magic; `<?XML` vs
  `CHEATENGINE` vs protected path); `:337` —
  `LUA_functioncall('onTableLoad',[true])` (before-load); `:998` —
  `LUA_functioncall('onTableLoad',[false])` (after-load).
- `Cheat Engine\ProcessHandlerUnit.pas:193` —
  `LUA_functioncall('onOpenProcess', [ptruint(processid)])`.
- `Cheat Engine\LuaTableFile.pas:189` — `findTableFile` registration.
- `Cheat Engine\luafile.pas` — `TLuafile.createFromXML` dual-branch
  embedded-file codec (Ascii85 + `ReadDWord` size prefix; hex branch
  read-until-EOF).
- `Cheat Engine\autoassembler.pas:338` / `:345` —
  `registeredsymbols.Duplicates := dupIgnore` /
  `allsymbols.Duplicates := dupIgnore`; `:2577-2578` — `label()`
  `val('$'+name)` identifier check; `:2585-2586` — disabled
  duplicate-declaration check; `:2599` / `:2603` — still-refused label
  errors; `:4164-4208` — delete-then-add runtime registration;
  `:732-798` — single-pass `removecomments`.
- `Cheat Engine\MemoryRecordUnit.pas:3500-3503` — `SetValue` typed
  pointer stores (`vtByte`…`vtQword`), the truncation behavior.

**Local-only (named, never reproduced in this document):** the
reference-table catalog artifacts under
`%LOCALAPPDATA%\Temp\opencode\refassess\` (per-run `blocked-catalog-*`
dumps) and the original reference tables under
`C:\Users\xboxl\code\reference-table-input-do-not-add-to-git`.
