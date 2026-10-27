# RT-5 API and table-level construct inventory

Status: 2026-10-23. Inventory step of the roadmap's RT-5
(runtime trainer parity), measured over the 151 local-only
reference-table paths (143 distinct byte hashes). This is a static,
read-only evidence document; the raw extraction artifacts remain
local-only (never in Git or release archives). The implementation half
of RT-5 (bounded host contracts, teardown rules, owned-target tests)
queues in section 9 after the remaining RT-4 packages land.

## 1. Purpose

RT-5 requires an inventory of every used CE Lua/AA API and every
game-facing table-level construct, including dynamic records,
callbacks, target threads, managed resolution, string hex view, and
byte-width dropdown semantics, with each item classified as:

- **Supported** — CT2Trainer handles it (module cited).
- **Staged/gated** — compiled into the plan behind an explicit gate.
- **Named-refusal gap** — fail-closed refusal; a remaining gap under
  the goal unless a scope decision is recorded.
- **No-effect (outside scope)** — purely visual/decorative; documented
  scope decision, no behavioral path required.

Scope rule (roadmap): parity is trainer/cheat handling and game-facing
effects. CE's editor and visual UI do not need replication; a UI API
used by a table to cause a game-facing effect still needs an equivalent
behavioral path; purely decorative UI calls can be classified
no-effect. "A legacy binary table, missing source asset, or
deliberately unsupported CE host API is a remaining gap under this
goal, even if its refusal is safe."

## 2. Method and inputs

- **Corpus:** 151 local-only reference tables (sibling directory
  `reference-table-input-do-not-add-to-git`, never in Git): 150 XML
  tables plus one legacy binary, `SuperMeatBoy.CT` (10,328 bytes,
  magic `CHEATENGINE\t`, CE 5.x era — RT-3 scope). Frozen manifest:
  `gap_inventory/reference-manifest.json` (151 paths, 143 hashes,
  source revision `ea233c26`).
- **Extraction:** local-only mechanical scans (XML structure census,
  AA first-word census, `{$...}` census, Lua call census over 49
  table `LuaScript`s plus 17 embedded `.lua` files). No corpus Lua or
  AA was executed. All scripts and artifacts live under
  `%LOCALAPPDATA%\Temp\opencode\refassess` (see section 10).
- **CE 7.5 reference (read-only):** local source tree
  `C:\Users\xboxl\code\cheat-engine-7.5`. Registration census:
  1,008 distinct global `lua_register` API names and 542 class method
  names across the tree; key files: `LuaHandler.pas` (446
  `lua_register` calls), `LuaStrings.pas` (`strings_add` + the
  `stringlist_add=strings_add` startup alias), `LuaStringlist.pas`,
  `LuaTableFile.pas` (`findTableFile`), `LuaTimer.pas`
  (`createTimerInternal` + generated `createTimer` shim),
  `OpenSave.pas` (`onTableLoad` dispatch, lines 337/998),
  `ProcessHandlerUnit.pas` (`onOpenProcess` dispatch, line 193),
  `autoassembler.pas` (AA directives; `usemono` has 0 hits tree-wide).
- **CT2Trainer source:** 0.16.3 on `main` (build
  `native-20261023T065015Z-afbc3eba`, in-build suite 3,421 OK / 25
  expected skips, `ce_inputs: []`).
- **Catalog baseline:** run `blocked-catalog-rt41` (2026-10-22, 0.16
  source, frozen manifest unchanged): 117,624 plan entries, 115,766
  supported (59,642 staged), 1,858 blocked, 1 legacy-binary load
  error.

## 3. Catalog baseline and gap ownership

The current 1,858 blocked rows are all attributed to upstream causes
in the roadmap's RT-2 root-cause map and owned by RT-3/RT-4.x
packages (each lands with synthetic case, full suite, catalog delta
with zero unexplained supported regressions, and a remeasure).
Leading current reasons and ownership:

| Current top reason (run `blocked-catalog-rt41`) | Rows | Class | Owner |
|---|---|---|---|
| Relative address cannot skip an addressless script/value ancestor | 331 | O1 | RT-4.3 |
| Required symbol has no unique supported provider (mouse_ovr 84, BaseAddress 80, loot_ptr 62, myPtr 44, BoardGameBoardUnit 40, GetAsyncKeyState 34, player_ptr 34, g_GameModule 32, goPlayer 28, myPtr3 25, pAttackInfo 21, bFlags 21, PlayerStats 20, p 20, LevelBasedXpArray 20, mProperties 20, pInventoryItemResource 20, Trampolines 19, PlayerCharacter 18, ...) | ~700+ across per-symbol rows | R1/R3/R4/R6/R7/O2 | RT-4.1 (done), RT-4.2, RT-4.6 |
| Pointer offset must be a hexadecimal integer literal | 53 | O3 | RT-4.3 |
| Dropdown choice exceeds the Byte value-type width | 27 | O6 | RT-4.4 |
| Unexpected trailing address expression tokens | 24+5 | O4 | RT-4.3 |
| Cleanup may only release symbols/allocations owned by this program | 17 | O5 | RT-4.5 |
| Strings require literal text display; the ShowAsHex byte view is unsupported | 15 | O7 | RT-4.4 |
| Dropdown contains an unsupported value expression | 13 | O8 | RT-4.4 |
| Relative address has no address-bearing ancestor | 10 | O9 | RT-4.3 |
| Unsupported AA directive: alloc (alloc/reassemble sub-errors) | 9+3 | O18 | RT-4.5 |
| Remaining small classes (O10 identifier 5, O12 aobscanregion 5, O13 indirect data 5, O14 `{$lua}`/`{$c}` 4, O15 usemono 4, O19/O20/O21 global-init 4+2+2, O22 createthread gate 2, O23/O24/O25 1+1+1, O26 dropdown-empty 1, O27 Type:Member 1) | 33 | — | RT-4.3/4.4/4.5 |
| Legacy-binary load error (`SuperMeatBoy.CT`) | 1 table | — | RT-3 |

Largest per-table blocked counts today: Octopath2 327, DS2 204,
re2_testicles 117, DeathStrandingDC (pair) 122/121, Witcher3 (pair)
91/93, Horizon (pair) 119/119, Cyberpunk 38, Subnautica_e67616 37,
SOTTR 29, ctts 28.

Items in this inventory that the catalog does **not** count (they are
table-level constructs, not plan rows): the `CheatCodes` code-patch
sections, embedded `.lua` files loaded by table Lua, the CE Lua API
gap list (section 7), and the no-effect constructs (section 8).
Those are the RT-5 implementation queue.

## 4. Table-level construct census (150 XML tables)

Counts are element occurrences across the corpus, with the number of
tables carrying the construct. Status refers to the 0.16.3 source.

### 4.1 Core record fields — supported

| Construct | Count | Tables | Status |
|---|---|---|---|
| `CheatEntries` / `CheatEntry` | 117,648 | 150 | Core record model (`table.py`, `compiler.py`) |
| `ID` / `Description` | 117,895 / 117,854 | 150 | Supported |
| `Address` / `Offsets` (pointer chains) | 105,205 / 14,835 | 112 / 88 | Supported; unsupported dialects are the RT-4.3/O1/O3/O4/O9/O10 classes |
| `GroupHeader` | 12,487 | 88 | Compiled as inert navigation headings (`compiler.py`) |
| `Options` (`moHideChildren` 12,900; `moManualExpandCollapse` 5,735; `moAllowManualCollapseAndExpand` 5,081; `moDeactivateChildrenAsWell` 4,941; `moRecursiveSetValue` 2,351; `moAlwaysHideChildren` 57; `moActivateChildrenAsWell` 53) | 13,420 | 112 | Supported: flag classes drive activation propagation, bind-activation and recursive set (`compiler.py`) |
| `ShowAsSigned` / `ShowAsHex` | 50,197 / 11,183 | 80 / 45 | `value_types.py`; ShowAsHex string views are the O7 class (RT-4.4) |
| `RealAddress` attribute | 2,059 | — | **No-effect:** CE's cached last-resolved address; the native runtime re-resolves addresses at attach |
| `Activated` attribute | 521 | — | CE's saved activation flag; CT2Trainer persists its own confirmed-ON state model (state lock), not this attribute |
| `Comments` / `Comment` / `DisassemblerComments` / `DisassemblerComment` | 24 / 87 / 8 / 87 | 24 / 8 | **No-effect:** editor annotations |
| `Color` | 36,426 | 105 | **No-effect:** presentation |
| `Offset` attribute (pointer-chain slots) | 36,896 | 88 | Supported; hex-literal-only slots are the O3 class (RT-4.3) |

### 4.2 Value-type options — supported

| Option | Count | Tables | Status |
|---|---|---|---|
| `ZeroTerminate` / `Unicode` / `Length` (String) | 1,423 each | 24 | `string_values.py` |
| `CodePage` | 1,338 | 20 | `codepage_contract.py` — pinned codec table, fail-closed on unknown values |
| `ByteLength` (Array of byte) | 1,247 | 25 | Supported |
| `ShowAsBinary` / `BitLength` / `BitStart` (Binary) | 1,347 each | 13 | `value_types.py` bit views |
| `Byte` elements (binary byte data) | 2,679 | 22 | Supported |

### 4.3 Dropdowns — supported, semantics in RT-4.4

| Construct | Count | Tables | Status |
|---|---|---|---|
| `DropDownList` | 2,047 | 54 | `value_links.py`; attributes `DisplayValueAsItem` 2,043, `DescriptionOnly` 1,600, `ReadOnly` 1,304 |
| `DropDownListLink` | 19,211 | 16 | Supported link resolution |
| Choice-width overflows (Byte record, choice `314`) | 27 rows | 3 (P3R pair + P3Reload) | O6 class — CE truncates (`SetValue` mod 2^8); CT2Trainer refuses until RT-4.4 lands (CE 7.5 probe recorded in the roadmap) |
| Expression dropdown choices | 13 rows | 2 (Borderlands3-V10, P4G) | O8 class — RT-4.4 (CE `SetValue` evaluates math/Lua expressions) |
| Description-only read-only dropdown | 1 row | 1 (小猫咪) | O26 class — RT-4.4 |

Byte-width dropdown semantics (O6/O8/O26) are the "byte-width dropdown
semantics" item of RT-5's deliverable list; they are owned by the
RT-4.4 lane, so they are not re-scoped here.

### 4.4 Hotkeys — fully supported

247 `Hotkey` entries in 37 tables (361 `Key` bindings; 81 hotkeys carry
a `Value` child for `Set Value`). Action census: Toggle Activation 97,
Activate 50, Set Value 48, Deactivate 19, Increase Value 18,
Decrease Value 15 — all six values are inside CT2Trainer's supported
sets (`hotkey_model.py::ACTIVATION_HOTKEY_ACTIONS` /
`VALUE_HOTKEY_ACTIONS`); per-record bindings are planned (WP-40) and
registered with first-wins conflict policy.

### 4.5 Scripts

| Construct | Count | Tables | Status |
|---|---|---|---|
| `AssemblerScript` (360 with `Async` attribute) | 8,004 | 147 | Native AA compiler (`aa_program.py`, NASM-backed) |
| `LuaScript` (table Lua) | 49 | 49 | Bootstrapped at attach (`lua_bootstrap.py`, `lua_host.py`); the API inventory is section 7 |

### 4.6 State and decoration — no-effect decisions

| Construct | Count | Tables | Decision |
|---|---|---|---|
| `LastState` (persisted CE value/activation state) | 2,701 | 42 | **No-effect.** CE-side persistence of last values/addresses; CT2Trainer keeps its own state model (confirmed-ON persistence, state lock). Reading CE's stale state back in would be a behavior divergence, not a parity win. |
| `ActivateSound` / `DeactivateSound` (children of `Hotkey`) | 79 / 49 | 18 | **No-effect.** Decorative toggle sound (CE plays it via `playSound(findTableFile(...))`); no game-facing effect. |
| Embedded images + `License.txt` (Cronos, DeathStranding pair, Resonance, SC2) | 5 png + 2 txt | 5 | **No-effect.** Footer/branding assets referenced by UI-only Lua. |

### 4.7 Symbols — supported

`UserdefinedSymbols` sections in 145 tables (512 `SymbolEntry`s across
31 tables, largest: trine2_32bit 203, SC2 72, Resonance 57, BatmanAK
33). Supported since WP-46 part 1 (static symbol seed) and hardened by
RT-4.1 symbol-provider fidelity (`lua_symbol_providers.py`, keep-first
duplicate policy).

### 4.8 Structures — no-effect in this corpus

16 tables define a `<Structures>` section with 1,067 structures and
25,531 elements (attributes: Offset/Vartype/Bytesize/DisplayMethod,
8,833 `RLECount`, 468 `PointerSize`, editor flags `AutoFill`/
`AutoCreate`/… 936 each). **No record in the corpus references these
structures**: none of the 16 tables has a `CheatEntry` with a
`<CustomType>` child (probe 3). The 6 `Custom`-vartype records live in
re2/re2_testicles and use table-Lua-registered types
(`registerCustomTypeAutoAssembler`) — the AP-08.7 staged gate (O11
class, 6 rows, RT-4.4). Decision: the `Structures` sections are
unreferenced editor metadata here; they surface as the
"Table-level sections not interpreted: Structures" warning with no
game-facing effect. If a future table references them, structure
runtime support becomes an implementation item.

### 4.9 Code patches (`CheatCodes`) — gap, game-facing

22 tables carry a `<CheatCodes>` section with 175 `CodeEntry` records
(175 `Before`/`Actual`/`After` byte sequences, 124 `AddressString`
module+offset targets, 51 `ModuleName`/`ModuleNameOffset`). Largest:
SOTTR 41, Subnautica 37, Yakuza_Kiwami_Remastered 18, trine2_32bit 13,
YLILWin64 (pair) 11+11, TheCallistoProtocol v1.2 7. CE presents these
as standalone activatable code patches (verify-before/apply-actual/
restore-after). CT2Trainer does not interpret the section
("Table-level sections not interpreted: CheatCodes" warning) — **gap,
RT-5 implementation item** (section 9, item B).

### 4.10 Integrity metadata — no-effect

21 tables carry `Signature`/`SignedHash`/`PublicKey` (table-integrity
signatures, e.g. the OCT and FRF families). **No-effect:** author
integrity metadata with no game-facing role; CT2Trainer does not
verify it and records it as an uninterpreted section.

### 4.11 Forms and trainer UI — outside scope

10 tables carry `<Forms>`: 7 embed a `CETrainer`
(`Class="TTrainerForm"`, `Encoding="Ascii85"`) — an Ascii85-encoded
alternative full-trainer form (AtomicHeart v1.2, Borderlands3-V10,
HellPie, METAPHORv9(STEAM), Scorn, TheCallistoProtocol v1.2,
YakuzaKiwami2_R); Resonance and SC2 embed `IconList`;
Yakuza_Kiwami_Remastered embeds `UDF1` custom forms. **Outside scope:**
purely visual UI. The table Lua that builds them runs to completion
against the WP-56 inert menu proxies; the record-toggling actions those
forms mediate are already covered by the record API. `table.py`
surfaces "Embedded CE forms are present; check UI conflicts."

### 4.12 Embedded files — mixed decision

9 tables embed files:

| Table | Embedded files | Decision |
|---|---|---|
| Cronos - The New Dawn v2 | plg.png, ctnd.ico | No-effect (UI assets) |
| DeathStrandingDC pair | OCTfooterlogo.png, License.txt | No-effect |
| Resonance, SC2 | FearlessRev_Footer.png | No-effect |
| Octopath2 | Starter.lua, Register.lua, Recorder.lua, UE.lua | **Gap:** loaded by table Lua |
| P5Strikers (+ copy) | Starter.lua, Register.lua, Reader.lua | **Gap:** loaded by table Lua |
| RiftApart | tFileList, AOBSaver.lua, Enable_Disable.lua, Scanner.lua, RA_Globals.lua, RA_Functions.lua, RA_PointerBaseFunctions.lua, RA_SymbolListDefinitions.lua, RA_TeleportFunctions.lua, RA_teleportLocations.lua | **Gap:** loaded by table Lua |

The table Lua loads the embedded helpers through
`findTableFile(name)` → `readStringLocal(tf.stream.memory,
tf.stream.size)` → `load(...)` (Octopath2 `loadLuaFile`; P5Strikers'
table-local `createObjectsFromLuaFiles` wrapper; RiftApart
`loadTableFiles` over the `tFileList` manifest). CT2Trainer neither
extracts embedded files nor provides `findTableFile`/`readStringLocal`
(named refusals), so the bootstrap of these four tables stops where it
hits the loader — **gap, RT-5 implementation item** (section 9, item
A).

### 4.13 Custom types

`Custom` vartype: 6 records in 2 tables (re2, re2_testicles), all with
a `<CustomType>` child naming a Lua-registered type
(`registerCustomTypeAutoAssembler` in the table Lua). No static
`<CustomTypes>` section exists in the corpus. Staged behind the AP-08.7
converter/write gate (O11, 6 rows, RT-4.4); runtime-only definitions
stay blocked until a converter/write gate exists (`custom_types.py`
contract, `CustomTypeAbort` payload).

## 5. Value types and address shapes

VariableType census (11 types, all handled except the staged `Custom`
gate): Byte 44,016 (64 tables), 2 Bytes 17,818 (32), 4 Bytes 14,955
(96), Float 14,374 (80), Auto Assembler Script 8,004 (147), 8 Bytes
1,866 (32), String 1,423 (24), Binary 1,347 (13), Array of byte 1,247
(25), Double 105 (17), Custom 6 (2).

Address-expression shapes (raw record addresses; unsupported dialects
are the RT-4.3 classes): relative 91,422 (50 tables), symbol_offset
6,527 (97), pointer_chain 4,268 (27), dotted 1,649 (18), hex_literal
932 (44), quoted_module_expr 292 (17), empty 91 (10), digit_leading 24
(4).

## 6. Auto Assembler directive inventory (8,004 scripts)

`{$...}` mode census: `{$lua}` 6,844 (114 tables), `{$asm}` 3,722 (73),
`{$STRICT}` 86 (6), `{$try}`/`{$except}` 2 each (2 tables). The corpus
uses no `{$if}`/`{$else}`/`{$endif}`/`{$process}`; the single
`{$r}`-shaped census hit is a false positive — it matched inside
Ascii85-encoded `CETrainer` content, not a real directive.

Supported directive set (`aa_program.py` dispatch + `aa_directives.py`
contracts), with corpus first-word census counts (occurrences /
tables):

| Directive | Corpus | Status |
|---|---|---|
| `label`, `registersymbol`, `unregistersymbol` | 4,545/126; 3,780/125; 2,823/124 | Supported (RT-4.1 tolerance for duplicate names) |
| `alloc`, `globalalloc` | 1,878/127 (+ globalalloc rows) | Supported (synthetic private addresses, documented) |
| `db` / `dw` / `dd` / `dq` (incl. WP-43 single-quoted ASCII strings) | 2,319/123; 53/12; 2,718/70; 668/61 | Supported |
| `nop`, `align` | 1,627/122; 517/25 | Supported |
| `aobscan` / `aobscanmodule` / `aobscanregion` | 47/10; 1,480/103; 148/12 | Supported (region bounds the O12 class, RT-4.5) |
| `define` | 175/24 | Supported (case-insensitive lookup) |
| `assert` | 121/19 | Supported (argument validation the O24 class, RT-4.5) |
| `reassemble`, `readmem` | 31/10; — | Supported (alloc sub-errors O18, RT-4.5) |
| `protect` / `unprotect` / `fullaccess` | — | Supported |
| `dealloc` | — | Supported (ownership checks the O5 class, RT-4.5) |
| `disassemble` | — | Supported (count-bounded, `MAX_DISASSEMBLE_COUNT`) |
| `createThread` / `threadWait` | 77/18 | **Gated:** no thread backend in the staged runtime (O22, 2 rows) — deliberate capability gate |
| `@`-cursors | — | Supported (WP-30d `@foo`/`@@name` program-local labels) |
| `{$if}`/`{$else}`/`{$endif}`/`{$define}` | 0 corpus hits | Supported (conditional preprocessor) |
| `{$asm}`/`{$ccode}`/`{$luacode}`/`{$strict}`/`{$try}`/`{$except}` | 3,722/73; 86/6; 2/2; 2/2 | Supported as no-op directives |
| `{$lua}` sections | 6,844/114 | Routed to the Lua program path (`lua_program.py`) |
| x86/x87 instructions (mov 4,614/122, jmp 3,555/126, cmp 1,586/83, jne 869/68, je 790/66, push 547/78, pop 533/72, call 505/31, test 495/57, add 312/65, ret 292/54, lea 264/38, sub 199/47, xor 197/49, fld 108/20, fstp 90/18, inc 98/19, movzx 79/27, shr 55/10, fmul 17/10, jb/ja 18/8 + 17/11, pushfq/popfq 16/8, movsx 13/5, int 12/7, popfd/pushfd 9/3, fsub 6/3, dec 4/4, fadd 4/3, fcomip 5/2, shl 3/2, enter/leave 2/2, fimul 2/2, neg 2/2, fst 2/1, popf 2/1, fdiv/loop/pushf 1 each) | — | Assembled by the bundled NASM |

Not present / deferred:

- `usemono` (2 scripts, 2 tables — ForgottonAnne, 小猫咪) and bare
  `use`: `usemono` has **0 hits in the CE 7.5 tree** — a newer-CE
  directive. Class O15 (4 rows), RT-4.5: reported as targeting a CE
  newer than 7.5 and stays blocked with a clear message (out of
  parity scope).
- AA `message()` directive: **no standalone usage in the corpus.** The
  91 census hits for `message(` are substring false positives —
  `mShowMessage(`/`showMessage(`/`messageDialog(` calls inside
  `{$lua}` sections. The catalog has 0 "Unsupported AA directive:
  message" blocks.

Census caveat: the first-word census also counts Lua statements that
start a line inside `{$lua}` sections (end 17,584, if 9,779, for 370,
while 120, then 4, break 20) — those are Lua syntax, not AA
directives.
## 7. Lua API inventory

Census scope: the 49 table `LuaScript` blocks plus the 17 embedded `.lua`
files (4 tables). 394 distinct call names were extracted and
cross-classified against (a) the CE 7.5 registration surface — 1,008
distinct global `lua_register` names and 542 class-method names across
the tree (authoritative file: `LuaHandler.pas`, plus `LuaStrings.pas`,
`LuaStringlist.pas`, `LuaTableFile.pas`, `LuaTimer.pas`) — and
(b) the CT2Trainer 0.16.3 Lua host surface (`lua_host.py`: whitelist,
bootstrap functions, proxy methods).

Result: 61 names match the CE global surface (one, `GetAddressList`,
casefold-only — CE 7.5 registers the name plus its first-character
case-flipped variant through the local `lua_register` wrapper
(`LuaHandler.pas:213-228`), so the uppercase call resolves there; the
CT2Trainer host registers only the lowercase form, so the uppercase
call is a named refusal here — a genuine, trivial host case-sensitivity
gap, not a newer-CE construct), 36 CE object methods, 28
stdlib/builtins, 269 table-local or obfuscated names.

Note: the census covered table Lua only. `{$lua}` sections inside
AssemblerScripts and `LuaCall` are routed through the same host
(`aa_luacall.py`), so the same named-refusal gap list applies there;
one additional name shows up only there, `playSound` (1 use, Metro
Exodus, decorative sound — no-effect).

### 7.1 Hosted CE global APIs (20)

| API | Uses (tables) | Host path |
|---|---|---|
| `createMenuItem` | 67 (7) | WP-56 inert menu proxy (`lua_host.py`) |
| `getMainForm` | 34 (8) | WP-56 inert form proxy |
| `shellExecute` | 31 (31) | safe no-op (WP-56), table-load warning |
| `showMessage` | 24 (2) | whitelist, logged |
| `openProcess` | 21 (9) | truthy no-op with identity verify (`lua_host.py:1695`) |
| `readInteger` | 15 (3) | whitelist |
| `getAddress` | 12 (5) | whitelist |
| `unregisterSymbol` | 12 (6) | whitelist |
| `getLuaEngine` | 10 (2) | bootstrap engine proxy |
| `writeInteger` | 10 (3) | whitelist |
| `getAddressList` | 9 (3) | bootstrap global (`lua_host.py:508`) |
| `getModuleSize` | 6 (4) | whitelist |
| `AOBScan` | 4 (4) | bounded static scan (`lua_host.py:782`) |
| `createFoundList` | 4 (4) | `lua_host.py:294` |
| `createMemScan` | 4 (4) | `lua_host.py:250` (scan object: `firstScan`, `waitTillDone`) |
| `registerSymbol` | 4 (2) | whitelist |
| `sleep` | 4 (4) | owned scheduler (`lua_host.py:642`) |
| `readPointer` | 2 (2) | whitelist |
| `writeQword` | 2 (2) | whitelist |
| `getAddressSafe` | 1 (1) | whitelist |

Also relevant: the `mono_*` managed-resolution APIs
(`LaunchMonoDataCollector`, `mono_enumDomains`, `mono_findMethod`,
`mono_invoke_method`) are whitelisted but unused by the corpus.

### 7.2 Named-refusal gaps (41 CE global APIs)

Undefined CE globals get the exact named refusal
(`Unsupported CE Lua API: <name>`, `lua_host.py:754`/`1719`; prefix
constant in `converter.py:26`). Fail-closed, but a remaining gap under
the goal unless a scope decision is recorded.

**Game-facing (14):**

| API | Uses (tables) | Notes |
|---|---|---|
| `findTableFile` | 8 (5) | embedded-file loader; required by table Lua in Octopath2, P5Strikers x2, RiftApart, Cronos (icon), Borderlands3 (sound) |
| `getProcessIDFromProcessName` | 15 (9) | bounded single-target lookup candidate |
| `getAutoAttachList` | 7 (7) | auto-attach registration; inert stringlist candidate (single-target model) |
| `getCEVersion` | 6 (4) | table version gates; decision needed (report CT2Trainer version vs refuse) |
| `getProcessList` | 6 (2) | used by `onOpenProcess` hook (Resonance, SC2) |
| `registerCustomTypeAutoAssembler` | 6 (2) | re2 custom types; AP-08.7 gate (O11, 6 rows) |
| `getSettings` | 6 (2) | CE settings query; bounded no-op candidate |
| `getOpenedProcessID` | 4 (4) | host has `getOpenProcessID`; alias gap (one line) |
| `integerToUserData` | 4 (2) | pointer/int conversion helper |
| `disassemble` | 2 (2) | `iced_disassembler.py` exists internally; bounded exposure candidate |
| `readStringLocal` | 2 (2) | string read with codepage semantics; string model exists |
| `registerAutoAssemblerCommand` | 2 (2) | P5Strikers custom AA commands; custom-directive path needed |
| `targetIs64Bit` | 2 (2) | architecture query; host knows target arch |
| `enumModules` | 4 (2) | bounded single-module answer candidate |

**Purely visual UI (27) — scope decision: no-effect, refusal stays:**
`messageDialog` (69/31 — user-facing dialog; `table.py:647` review
warning at load; decision item E), `control_setVisible` (16/4),
`wincontrol_getControl` (16/4), `getMemoryViewForm` (14/6),
`getStructureCount` (14/2), `getStructure` (16/2), `createButton`
(9/7), `createPanel` (8/2), `createForm` (7/7), `createFont` (5/5),
`createLabel` (5/5), `component_getComponent` (4/4), `createPicture`
(4/2), `createStructure` (4/2), `enumStructureForms`
(4/2), `setMethodProperty` (4/4), `menu_getItems` (4/2),
`createCheckBox` (2/2), `createComponentClass` (2/2),
`createOpenDialog` (2/2), `createStructureForm` (2/2), `createImage`
(1/1), `GetAddressList` (1/1 — the uppercase variant of the hosted
`getAddressList`; CE 7.5 also registers the first-character case-flipped
variant (`LuaHandler.pas:213-228`), so the call resolves there and the
named refusal on the CT2Trainer host is a genuine, trivial
case-sensitivity gap, not a newer-CE construct; the AtomicHeart
dark-mode / rainbow-background usage is purely visual, so the no-effect
decision stands on usage grounds),
`timer_onTimer`/`timer_setEnabled`/`timer_setInterval` (1/1
each, legacy TTimer helper style).

### 7.3 CE object methods (36 names)

Covered by host proxies: `add` (stringlist object, `lua_host.py:377`),
`getMemoryRecordByID`/`getMemoryRecordByDescription` (addresslist
proxy, `lua_host.py:219`), `doClick` (WP-56 menu proxy),
`firstScan`/`waitTillDone` (scan object), `execute`/`Execute`,
`initialize`, `clear`.
UI-only (no-effect): `hide`/`Hide`, `show`/`Show`, `loadFromStream`/
`LoadFromStream`, `getBitmap`, `setSize`, `SendToBack`, `draw`,
`getCanvas`, `setBevelOuter`, `addElement`, `addToGlobalStructureList`,
`removeFromGlobalStructureList`, `getElementByOffset`,
`getReferencedStrings`, `setOnlyOneResult`, `getOnlyResult`,
`disableAllWithoutExecute`, `getMemoryRecord`, `Destroy`,
`loadFromFile`/`saveToFile` (stringlist file access refused as outside
the profile, `lua_host.py:424`).
Gap: `createMemoryRecord` (2/2) — dynamic record creation, not
supported by the addresslist proxy.

### 7.4 Table event callbacks

CE dispatches `onTableLoad(before)` (OpenSave.pas:337/998) and
`onOpenProcess(processId)` (ProcessHandlerUnit.pas:193) via
`LUA_functioncall`. The CT2Trainer host does not dispatch them. Two
tables define `onOpenProcess` (Resonance, SC2): it sets
`myGame = getProcessList()[processId]`, and the table scan Lua uses
`getAddress(myGame)` — a game-facing dependency chain (item D).

### 7.5 Non-CE names (269)

Lua stdlib (28) and table-local/obfuscated helpers (241): no action.
Related non-census CE names: `stringlist_add` (5/5 — CE global alias of
`strings_add`; host has the stringlist object `.add` but no global),
`playSound` (decorative, no-effect), `createTimer` (CE generated shim;
host provides its own, `lua_host.py:650`), `redirectPrint`
(2/2 — table-local in the FearlessRev tables),
`createObjectsFromLuaFiles` (2/2 — table-local wrapper in P5Strikers).

## 8. Scope decision register

**Game-facing gaps (implement or document as residual):**

- A. Embedded-file extraction + `findTableFile`/`readStringLocal` host
  contract — 4 tables (Octopath2, P5Strikers + copy, RiftApart).
- B. `CheatCodes`/`CodeEntry` code patches — 22 tables, 175 entries
  (SOTTR 41, Subnautica 37, Yakuza_Kiwami_Remastered 18,
  trine2_32bit 13, YLILWin64 pair 11+11, TheCallistoProtocol 7, …).
- C. Process-info API family (14 names, section 7.2 game-facing list)
  incl. `getOpenedProcessID` alias, `stringlist_add`,
  `createMemoryRecord`.
- D. Callback dispatch `onOpenProcess`/`onTableLoad` — 2 FearlessRev
  tables, `myGame` chain.
- E. `messageDialog` decision — 31 tables, 69 calls; currently named
  refusal + load-time review warning.

**No-effect / out-of-scope (documented):**

- CE UI family (26 global APIs + 18 object methods, section 7.2/7.3);
  `Forms` (10 tables), `CETrainer` forms (7 tables, Ascii85
  `TTrainerForm`), `IconList` (2), `UDF1` (1); `Signature`/
  `SignedHash`/`PublicKey` (21 tables); `LastState` (42 tables);
  `ActivateSound`/`DeactivateSound` (128/18 tables); embedded images
  and `License.txt` (5 tables); `Color`/`GroupHeader`/`Comments`/
  `DisassemblerComments` presentation; `RealAddress` attribute (2,059);
  `Structures` sections (16 tables — unreferenced by any record;
  surfaced as warning); `playSound`, legacy timer helpers.
- Thread backend: `createThread`/`threadWait` AA directives (77/18
  tables) gated behind the O22 capability gate (2 catalog rows).

## 9. Remaining RT-5 work (implementation queue)

Ordered after the RT-4 lanes land (RT-4.6 219 rows, then RT-4.2
1,085 rows last):

1. Item A — embedded files + `findTableFile`/`readStringLocal`.
2. Item C — bounded process-info APIs (single-target semantics,
   inert auto-attach stringlist, arch query, alias fixes).
3. Item D — `onOpenProcess`/`onTableLoad` dispatch for the 2
   FearlessRev tables.
4. Item B — code-patch plan path for `CheatCodes` (or recorded
   scope decision).
5. Item E — `messageDialog` decision (no-op with review flag vs
   refusal).
6. Item F — ratify the no-effect register (section 8) with tests.
7. Item G — `createThread`/`threadWait` backend decision (O22).

Each item follows the per-package protocol: leading-table inspection,
independently authored synthetic cases, class contract as testable
assertion, owned-target runtime tests where effects matter, full
suite green (`CT2TRAINER_NASM`), catalog delta with zero unexplained
supported regressions, remeasure, docs updated in the same change.

## 10. Evidence and provenance

- Corpus: `C:\Users\xboxl\code\reference-table-input-do-not-add-to-git`
  (151 paths, 143 distinct hashes; frozen manifest
  `gap_inventory/reference-manifest.json`, source revision `ea233c26`;
  150 XML + `SuperMeatBoy.CT` legacy binary, 10,328 bytes, magic
  `CHEATENGINE\t`).
- Catalog baseline: run `blocked-catalog-rt41` (2026-10-22):
  117,624 plan entries, 115,766 supported, 59,642 staged, 1,858
  blocked, 1 legacy-binary load error; per-reason and per-table
  breakdown in the local artifact
  `%LOCALAPPDATA%\Temp\opencode\refassess\rt5\rt5_catalog_dump.txt`.
- CT2Trainer source inspected: 0.16.3 on `main` (build
  `native-20261023T065015Z-afbc3eba`; suite 3,421 OK / 25 expected
  skips, `ce_inputs: []`).
- CE 7.5 reference (read-only, `C:\Users\xboxl\code\cheat-engine-7.5`):
  `LuaHandler.pas` (446 `lua_register` calls; tree-wide 1,008 global +
  542 method names), `LuaStrings.pas`/`LuaStringlist.pas`
  (`strings_add`, `stringlist_add` alias, stringlist class),
  `LuaTableFile.pas:189` (`findTableFile`), `LuaTimer.pas:166-176`
  (`createTimerInternal` + `createTimer` shim), `OpenSave.pas:337/998`
  (`onTableLoad` dispatch), `ProcessHandlerUnit.pas:193`
  (`onOpenProcess` dispatch), `autoassembler.pas` (AA directives;
  `usemono` 0 hits — newer-CE directive).
- Extraction tooling and raw artifacts (local-only, never shipped):
  `%LOCALAPPDATA%\Temp\opencode\refassess\` — `rt5_inventory.py`,
  `rt5_probe2.py` … `rt5_probe11.py`, `rt5_classify3.py`,
  `ce_lua_api_full.py`; raw outputs `rt5_inventory_raw.md`/`.json`,
  `rt5_probe*.txt`, `ce_lua_api_surface.txt`,
  `rt5_classification3.txt` (final 61/36/28/269 split).
- Suite baseline and build evidence: `STATUS.md`,
  `plans/TRACKING.md`, `documentation/native-progress.md`
  (2026-10-23 entries).
