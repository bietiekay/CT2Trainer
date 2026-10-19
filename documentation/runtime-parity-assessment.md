# CT2Trainer — Reference-Corpus Blocked & Missing Feature Assessment (Wave 4)

**Date:** 2026-10-18 · **Base:** `main` @ `2fe08f9` (0.15, build
`native-20261018T055505Z-39f20180`) · **Status:** root-owned analysis,
closes the "identify all blocked and missing features in all reference
tables" request; feeds the Wave-4 work packages (WP-43…WP-57).

## 1. Scope and method

Three independent evidence planes, all reproducible from committed code
plus the local-only reference corpus
(`C:\Users\xboxl\code\reference-table-input-do-not-add-to-git`, never
committed):

1. **Plan-level census** — every distinct (SHA-256) table (143 of 302
   files) compiled with `compile_table` at an explicitly resolved
   process name (most frequent `.exe` literal in the file). Raw outputs:
   `Temp\opencode\reason-dist-out.json`, `retry31-out.json`,
   `uds-corpus2-out.json`, `roots2-out.txt`, `roots3-out.txt`,
   `gcircle-blocked.txt`, `probe5-out.txt`, `probe6-out.txt`.
2. **Runtime audit** (Lane C, `reference-assessment/raw/
   runtime-parity-C-code.md`) — bucket classification (A implemented +
   fixture-tested, B plan-only, C fail-closed gap, D implemented but
   default route refuses until an owned live backend exists) of all 42
   in-scope features + additional product features; 459 focused tests
   green at the base commit.
3. **CE 7.5 behavior reference** (Lane E, `reference-assessment/raw/
   runtime-parity-E-ce-behavior.md`) — ten behavior contracts with
   file:line evidence from the read-only CE source tree (clean-room
   boundary: behavior reference only, no copied code).

The four focus tables (Ace7 ColonelRVH, Ace7Gamefrf, PlagueTale
Innocence, PlagueTale Requiem — all hash-identical to the corpus
copies) were analyzed record-by-record; every blocked reason class in
the census below was root-caused by targeted provider lookups.

## 2. Plan-level census (all 143 distinct tables)

**Headline:** 117,308 plan entries → **112,581 supported** (96.0 %),
**4,727 blocked** (4.0 %), 12,908 headings. The canonical catalog
(GOAL-2 measurement, auto process-detection) stands at 7,577 /
117,624 with one whole-table error (SuperMeatBoy legacy binary); the
two views differ only in process resolution of the 31 tables CE
stores without a unique EXE name. The canonical catalog remains the
authoritative closure metric; this census is the feature-planning
view.

### 2.1 Complete reason-class inventory (4,727)

| # | Reason class (normalized) | n | Top attribution | Root cause | Disposition |
| --- | --- | ---: | --- | --- | --- |
| 1 | `Required symbol has no unique supported provider: <sym>` | 2900 | Lust 392, DS2 375, re2_t 226, HorizonFW 197, AtomicHeart 159, HellPie 137, Oregon 136, Callisto 136 | cascades — per-symbol roots in §3 | via the owning root WPs |
| 2 | `Required symbol provider is blocked.` | 799 | AtomicHeart 267, Scorn 266, HellPie 266 | the kept provider record is itself blocked (symbol dependency cycle, see 3.2) | WP-49 |
| 3 | `Relative address cannot skip an addressless script/value ancestor.` | 330 | Octopath2 327, HFW 1, AtomicHeart 1, DS2 1 | script parent with empty `<Address/>` writes `mr[<id>].address = …` from record Lua (dynamic script-parent provider) | WP-50 |
| 4 | `Dropdown link target is missing: '<target>'.` | 240 | P3Reload 204, P4G 23, YakuzaK2 7, SMB3Dfrf 6 | dangling `DropDownListLink`; CE shows an empty list and the record stays writable | WP-45 (demote to plain value + warning) |
| 5 | `Symbol provider duplicate: <sym> (kept provider N).` | 172 | SOTTR 38, BL3-V10 14, ForgottonAnne 11, qt-ds-1/2 9+9, Kena 7, Innocence 7, Cyberpunk 7 | keep-first dedupe is selection-independent (verified D1–D4 probes) — user cannot activate the alternative variant | WP-45 (selection-aware dedupe) |
| 6 | `Pointer offset must be a hexadecimal integer literal.` | 52 | Cyberpunk 30, Callisto 9, working.ct 9, SOTTR 3, HFW 1 | decimal `<Offset>` values (CE parses them with `StrToIntDef`) | WP-45 (accept decimal/signed) |
| 7 | `Static AA envelope: <…>` | 35 | DS2 14, BatmanAK 3, HFW 2, Witcher3 2+2, SOTTR 2, re2_t 2, 小猫咪 2 | mixed: single-quoted strings (`'======>G25'`), cleanup-ownership, others | WP-43 (string share) + per-case |
| 8 | `Dropdown choice '<n>' exceeds the value-type width.` | 30 | P3R v1/v4/v5 9 each, P3Reload 3 | choice 314 on a Byte record; CE semantics ambiguous (truncates) | blocked-keep (named reason; documented) |
| 9 | `Unsupported AA directive: <name>.` | 29 | Subnautica_e 5, HFW 2, trine2 2, ForgottonAnne 2, BatmanAK 2, … | mostly the single-quoted-string-in-data share (Requiem id15 shape); remainder per-case | WP-43 + per-case |
| 10 | `Unexpected trailing address expression tokens.` (native + plain) | 29 | DS2 10, GingaForce 8, Penny 3, REZ 3, qt-ds 2+2, rayman 1 | expression-syntax edges; DS2 share = Lua-assembled builder scripts | WP-51 (DS2 share) + per-case |
| 11 | `Unsupported address expression: '<sym:method…>'.` | 13 | Subnautica 6, YLIL 3+3, LustForDarkness 1 | managed method labels used as bare addresses; live IL2CPP resolver open (bucket D) | documented (AP-11 live backend) |
| 12 | `Dropdown contains an unsupported value expression.` | 13 | BL3-V10 12, P4G 1 | choice rows carrying expressions | per-case investigation |
| 13 | `Address expression exceeds the bounded indirection depth (2 …).` | 12 | AtomicHeart 5, Oregon 2, YLIL 1+1, Callisto 1, Scorn 1, HellPie 1 | corpus chains reach 4–5 derefs (`[[[[X]+38]+270]+140]+230`) | WP-45 (raise bound to 6, resolver already generic) |
| 14 | `Strings require literal text display; the ShowAsHex byte view is unsupported.` | 12 | DS2 9, HFW 3 | string codec is literal-text only (GC-A6 decision, W2-A) | blocked-keep (reaffirmed) |
| 15 | `Script has no registered symbols or guarded byte-patch action.` | 10 | re2 2 (incl. `DO NOT ACTIVATE`), re2_t 2, P5S 1+copy, Sackboy 1, Ace7 1, BL3 1, Rage 1 | comment-only / no-op scripts (Ace7 credits record 9237 shape) | WP-44 (demote to inert supported no-action; CE: toggleable no-op) |
| 16 | `Relative address has no address-bearing ancestor.` | 10 | SOTTR 10 | degenerate addressless header trees (GC-B7) | blocked-keep |
| 17 | `Symbol must contain ASCII letters, digits or underscores.` | 7 | recolored 5, Octopath 2 | dotted/odd symbol spellings in table | blocked-keep (named reason; symbol-table contract) |
| 18 | `Indirect address expressions are not supported in the data dialect.` | 5 | SandFall ×5 versions (same table) | value-path expression still stricter than the WP-30 bounded profile | per-case |
| 19 | `Lua, C and compiler/preprocessor directives are unsupported.` | 5 | BL3-V10 4, Resonance 1 | out-of-profile `{$…}` directives (WP-26 boundary) | blocked-keep |
| 20 | `Program cannot combine wildcard cleanup with externally owned symbol <sym>.` | 3 | Octopath2 3 | Wave B2 guard (WP-37) — deliberate | blocked-keep |
| 21 | `Symbol dependency cycle is unsupported.` | 3 | AtomicHeart 1, Scorn 1, HellPie 1 | two pointer scripts mutually require each other's symbols; CE resolves lazily | WP-49 (with the 799-cascade class #2) |
| 22 | `Custom value type 'RE2_Hrs'/'RE2_Mins'/'RE2_Secs' …` | 6 | re2 3, re2_t 3 | table-Lua-defined custom types; no static definition + write gate (AP-08.7) | blocked-keep until codec program |
| 23 | `Invalid address expression near '.3'. …` | 2 | re2 1, re2_t 1 | versioned symbol spellings (`dCusWetAmount.3`) colliding across records | per-case |
| 24 | `Unsupported AA syntax or machine instruction: …` | 2 | re2_t 1, Starfield 1 | per-case | per-case |
| 25 | `Global initialization requires one direct ENABLE cursor.` | 2 | Resonance 1, SinkingCity 1 | globalalloc profile residual (GC-C9 keep shape) | blocked-keep |
| 26 | `Labels inside a global initializer are outside the direct literal profile.` | 2 | SinkingCity 2 | same family | blocked-keep |
| 27 | `Nested AA comments are unsupported.` | 1 | RDR2 1 | bounded comment dialect | blocked-keep |
| 28 | `Unterminated source block comment.` | 1 | SonicFrontiers 1 | authoring bug | blocked-keep |
| 29 | `Read-only dropdown has no concrete literal choices.` | 1 | 小猫咪大城市 1 | empty dropdown | per-case |
| 30 | `Quoted atoms must be module basenames.` | 1 | Cyberpunk 1 | quoted atom that is not a module | per-case |
| 31 | `createThread()/threadWait() are gated …` (in 9's native share) | 2 | Witcher3 1 (`Call Function`), … | no thread backend in the shipped profile (WP-36 gate) | blocked-keep until live backend (AP-11) |
| 32 | `Table-level sections not interpreted: UserdefinedSymbols.` (warning) + UDS-only provider blocks | 49 blocked | SinkingCity 24, Resonance 10, trine2 3, re2_t 3, SandFallV5 2, trine3 2, BatmanAK 1 | `<UserdefinedSymbols>` section ignored by design — see §3.3 | WP-46 (interpret UDS as table-level static symbols) |

## 3. Root-cause evidence (probe-verified)

All probes were minimal synthetic tables compiled at the base commit
(`compile_table`), plus targeted provider lookups on the reference
tables (read-only; raw outputs in `Temp\opencode\*probe*-out.txt`,
`roots2-out.txt`, `roots3-out.txt`).

### 3.1 Single-quoted string data literals (WP-43)

`db 'Console'`, `db '======>G25'`, `db 'Ryo '`, `db 'Class'` — the
data dialect only accepts double-quoted strings (already supported via
`_literal_data`, size calc and patch generation); single-quoted values
fall into the bounded expression parser and fail. Evidence: P9
(double-quote `db` supported) vs P12 (single-quote `db` blocked).
Blocked: Requiem id=15 provider (4 consumer records), Witcher3
provider id=10070 (mouse_ovr 43 + loot_ptr 31 + str_ptr consumers),
AtomicHeart id=357230, plus the shared `Unsupported AA directive` /
`Static AA envelope` records of class #7/#9.

### 3.2 Pre-ENABLE `registerSymbol` (WP-44)

The pre-`[ENABLE]` envelope allows only `define`/`label`
(`aa.py:466-467,499,533`; `aa_program.py:863-864`). CE allows
`registerSymbol` before `[ENABLE]`. Evidence: L1 (blocked), L2b/L2c
(multi-token `label` + `registersymbol` with `alloc`+`resb` — supported,
provides extracted). Blocked: Lust from Beyond id=5 `[[POINTERS]]`
script (provider of `_playerBase`; 392 consumers + 29). Every other
construct in that script was individually probed and is supported
(managed define `module:Method` = L3, `resb`/`nop 6` = L4, 3-arg
`alloc` with `$process` = P1, duplicate `registersymbol` = P4b,
`unregistersymbol(*)` = P5, case-insensitive `deAlloc` = P8,
pointer-chain label definition = P6).

### 3.3 `UserdefinedSymbols` (WP-46 — user-reported, Great Circle)

Table-level `<UserdefinedSymbols>` with `<SymbolEntry><Name>…</Name>
<Address>HEX</Address></SymbolEntry>` entries is currently ignored
(`compiler.py:1303` warning). Corpus-wide (correct `SymbolEntry`
format, `uds-corpus2-out.json`):

- **31 tables** carry a non-empty UDS section (72 symbols in
  TheSinkingCity, 57 in Resonance, …).
- **49 records blocked solely because the symbol's only provider is a
  UDS entry**: TheSinkingCity 24, Resonance 10, trine2 3, re2_testicles
  3, SandFall V5 2, trine3 2, BatmanAK 1.
- Additionally **30 records in Subnautica and 7 in Fallout4 reference
  UDS symbols but stay supported** (a script also registers them — the
  UDS entry is redundant there; conflict rule: a supported script
  registration must keep winning, UDS fills gaps only).
- **Warning noise**: CE 7.x writes an empty self-closing
  `<UserdefinedSymbols/>` into *every* table (TheGreatCircle_Plus21
  has it at line 1101 with no content). The current warning fires for
  that empty tag on every CE-authored table — it must be suppressed
  for empty sections.
- Disposition: interpret `SymbolEntry` as table-level static symbol
  definitions (hex absolute address; non-hex fail-closed with a named
  reason); available in address expressions and AA symbol resolution;
  never shadows a supported script provider.

The 6 blocked records of TheGreatCircle_Plus21 are unrelated to UDS:
all cascade from script id=33 "Set AP & Currency Amounts", which needs
the external UE symbol `GetCurrency` (not in the table) and the
split-byte AOB token `s1.2` (unsupported by stock CE 7.5 itself — the
table's own note says to skip the entry). Fail-closed is correct there.

### 3.4 Lua-provided symbols (WP-46b)

`registerSymbol("<literal>", expr)` inside record/table Lua is not
extracted into `provides`: P3Reload provider id=1701070941 (supported
one-shot, empty `[disable]`, `provides: []`; 124 consumer cascade),
AtomicHeart `BaseAddress` ×15, DS2 `g_GameModule` ×10 (3-arg
`registerSymbol("g_GameModule", u, true)`), re2 `luaCall(lua_aobscan(
"sym",…))` (luaCall symbol provision missing — part of WP-48 scope).

### 3.5 Symbol dependency cycle (WP-49, design gate)

AtomicHeart id=239469 (registers `Character_Pointer`, requires
`character_pointer`) + id=239470 (duplicate, keep-loser) → the whole
799-record "Required symbol provider is blocked." cluster
(AtomicHeart 267 / Scorn 266 / HellPie 266, incl. `Esau_base` ×600 via
id=239474 requiring `Character_Pointer`). CE resolves symbol
dependencies lazily at patch time; CT2Trainer's plan is a one-pass
fixed-point — iterative/lazy resolution needs a design note.

### 3.6 Dynamic script-parent providers (WP-50, design gate)

Octopath2 ×327: value children (`+220`, …) hang under a script record
(id=23492, `moHideChildren`, empty `<Address/>`); record Lua writes
`mr[N].address = …` at runtime (`createTimer`; `mr[2].address = nil` in
DISABLE). Extend the WP-38 `address_provider` contract to script
parents via static extraction of the `mr.address` writes.

### 3.7 Lua-assembled AA programs (WP-51)

DS2 provider id=87496 `[ Initialize ]` (10,629 chars) assembles the AA
script in Lua (`local _script = [[…]]..[[[ENABLE]…]]`) → "Enable
section has no executable patch or data". ~412 DS2 blocked records
mostly cascade from this provider + myPtr/myPtr2/myPtr3/p. Plan-level
admission when the record Lua provably calls `autoAssemble`; the
engine path already exists (lua_dynamic_assembler bucket A).

### 3.8 Selection-independent provider dedupe (WP-45)

D1–D4 probes: the kept provider of `Symbol provider duplicate` blocks
alternative providers even when the kept record is not selected — the
user cannot activate a variant. Fix: selection-aware dedupe.
Same compiler cluster: decimal `<Offset>` literals (52; `compiler.py:
129-147`), missing dropdown-link target demotion (240: P3Reload 204,
P4G 23, YakuzaK2 7, SMB3Dfrf 6 — CE shows an empty list, the record
stays writable), indirection bound 2→6 (12 records use 4–5 derefs).

### 3.9 Sinking City 2 field case (2026-10-18, user report)

The user ran the 0.15 trainer on the downloaded `TheSinkingCity2.CT`
(LIOBOSS, Build.24671220) and supplied the 0.15 debug log plus a
"Plus 27" trainer EXE from the internet. Full analysis and artifacts:
`reference-assessment/raw/sinking2-extract-crosscheck.md` (local-only) +
`Temp\opencode\sinking2\extracted\` (extracted CT, master-draft CT).

- **Inf Health fails on a multi-match AOB.** `F3 0F 5F C7 F3 0F 11 87 60 02
  00 00` matches multiple times in the installed build; CT2Trainer's
  `scan_module` is fail-closed on >1 match, CE `aobscanmodule` takes the
  first (lowest-address) match → **WP-55**.
- **Inf Items fails: pattern absent.** `8B 42 48 41 2B C0` was not found in
  the full 195 MiB module scan (512 MiB `MAX_SCAN_SIZE` not a factor) —
  table/build mismatch, correct fail-closed; verify installed build.
- **record-Lua CE globals missing** (id 200 attach record `OpenProcess`,
  id 198 CompactMode `getMainForm`/`createMenuItem`, id 231 support link
  `ShellExecute` behind `syntaxcheck`): raw nil-call errors instead of
  named reasons; CT2Trainer already auto-attaches, so an `OpenProcess`
  no-op stub is semantically correct → **WP-56** (corpus-wide: Lane R #4).
- **EXE forensics (Plus 27 Trainer):** ARM64 native "27-item modifier"
  (二十七项修改器), no embedded .CT XML (no CT markers, no zip/lzma, no
  encoded variants); embedded AA script(s) + UTF-16 label block listing
  all 27 features (God Mode, Infinite Health/Revives/Ammo, No Reload,
  Super Accuracy, No Recoil, Rapid Fire, Full-Auto, Super Damage/One Hit
  Kills, Damage/Defense Multiplier, Highlight Collectibles, Edit Item
  Count, Infinite Consumables, Ignore Crafting Requirements, Edit Talent
  Points, speed settings, FOV, Fly Mode, Teleport). None of the LIOBOSS CT
  patterns occur in the EXE (raw bytes, AA text, or hex strings) — the
  two trainers hook different functions (independent implementations).
- **Master table:** union of LIOBOSS entries + extracted script(s) +
  native-only feature reference headers — built as scratch draft.
- **Planned case-31** pins the WP-55/WP-56 shapes (multi-match AOB +
  record-Lua globals + empty UDS tag + pointer value child).
- **Placeholder-token AOB (GC-E20):** 26 of the 30 Plus-27 patterns use
  the trainer's `s1`/`s1.2` 2-byte runtime displacement tokens (plus the
  external region symbol `RapidFireSearchBegin`); stock CE 7.5 cannot parse
  them — same class as the Great Circle `s1.2` records. Candidate
  **WP-57 (design)**: wildcard scan + captured-byte restore.

## 4. Runtime parity gaps (Lane C top-10 + CE contracts, Lane E)

| # | Gap | Evidence | CE 7.5 contract | WP |
| --- | --- | --- | --- | --- |
| 1 | allocation-only programs cannot be enabled | `link_program` emits `blocks: []` (`aa_program.py:1993-1996`); `hooks.py:521-523` nonempty guard; staged at `engine.py:3452` | valid no-op write; symbols only | WP-47 (integrated 2026-10-19, lane w4-c @ `ee07b60`) |
| 2 | no OS hotkey capture route; programmatic dispatch only | `RegisterHotKey` absent; `dispatch_hotkey` `engine.py:4210-4218`; Ace7 id=8848 group-heading hotkey (`moHideChildren=1`, Action=Activate, keys 18,45) | hotkeys load-time append, no record-type gate (group hotkeys work) | WP-53 |
| 3 | table-Lua phase 2: no persistent `createTimer` + table-scope symbol writes | GoW `goPlayer` ×28; corpus-wide `createTimer` ×2822 | table Lua persists across attach, symbols table-scoped | WP-54 |
| 4 | broker scan/utility surface missing | `memscan.Result` + `OnlyOneResult` absent; `firstScan` requires exactly 14 args with `(soExactValue, 8, 'rtRounded')` so nil rounding rejected (`lua_host.py:1310-1315`); found-list proxy lacks `getCount()`/`getAddress(i)`; `createStringlist` + `.add` + `fullAccess` absent (`lua_host.py:305-313`) | Requiem id=88229 + P3Reload provider plan-supported but runtime-fail | WP-52 (integrated 2026-10-19, lane w4-f @ `0c5e519`; `getAddress(i)` 0-based per CE source) |
| 5 | dynamic address providers | runtime dynamic address providers shipped in 0.15 (WP-38) | re-resolve per evaluation — contract holds | — (done) |
| 6 | one-shot persistence | CT2Trainer persists only confirmed ON (wish model) | CE one-shot = enable-only, no persistence | intentional extension (keep) |
| 7 | symbol resolution order | keep-first dedupe vs CE delete-then-add last-wins | CE last registration wins | keep-first = safe narrowing (documented) |
| 8 | prefix-cut byte patches | 0.15 fix: `db 90 E9` over 6-byte conditional jump proven at link + re-verified at stage | standard CE practice | — (done, confirmed) |
| 9 | duplicate-ID tolerance | tolerated with warning (W1) | CE tolerates | keep |
| 10 | `{$…}` directive / phase splitting | bounded dialect (WP-26) | CE superset | documented boundary |

Lane C bucketing: A (implemented + fixture-tested) = 29, C
(fail-closed gap) = 5, D (implemented, default route refuses until an
owned live backend exists) = 8; 459 focused tests green at the base.

### 4.1 Complementary frequency census (Lane R, `runtime-parity-R-corpus.md`)

Full-corpus usage census (151 files / 117,624 entries, 1 legacy-binary
parse error: SuperMeatBoy; 24 dup-ID drops in Octopath): all §1 core
APIs verified host-supported; one-shot share 72.5 % (ref) vs 79.0 %
(pinned). Top runtime-parity candidates by frequency × difficulty
(counts = raw occurrences / tables):

| # | Candidate | Counts | Disposition |
| --- | --- | --- | --- |
| 1 | record lifecycle callbacks (`onMemRecPostExecute`, `disableWithoutExecute`, `onEnable`/`onDisable`) | 2,858/4, 2,856/2, 9/5 | Wave-5 backlog (large surface, new design gate) |
| 2 | `synchronize` (UI-thread marshaling) | 2,650/9 | Wave-5 backlog |
| 3 | table-Lua persistent `createTimer` bootstrap | 8 tables | WP-54 (batch 4) |
| 4 | GUI/menu surface (`getMainForm`, `createMenuItem`, `addCompactMenu`, `messageDialog`, …) | ~550/~40 | Wave-5 backlog (trainer UI scope) |
| 5 | dynamic record management (`createMemoryRecord`, `appendToEntry`, `setAddress`, `setDescription`, `setType`, …) | ~640/~15 | Wave-5 backlog |
| 6 | dropdown-link scale | 19,211 linked / 12 tables | mostly shipped (WP-24/27/34); +35 byte-array dropdowns, 11,183 `ShowAsHex` = blocked-keep |
| 7 | parent-activation propagation | 4,950 / 60+ tables | shipped (cascade contracts) |
| 8 | recursive parent value (`moRecursiveSetValue`) | 2,351 / 13 | shipped (recursive value write) |
| 9 | process-surface extension (`openProcess`, `ShellExecute`, `aobscanEx`, `writePointer`, …) | ~390/~45 | Wave-5 backlog (live-backend adjacent, AP-11) |
| 10 | deep pointer chains + expression addresses | 9,417 chained (Borderlands3 max 6 levels) + 6,410 expression forms | WP-45 indirection bound 2→6 (batch 2) |

Hygiene flags from Lane R: 2,674/2,675 "unresolved" addresses are
negative relative offsets (census regex artifact — the product
`parse_expression` handles unary minus); the denominator `lib.py`
allowlist/gap classes are stale (registerlabel/fullaccess now
product-supported via WP-31) — tooling follow-up owned by root.

## 5. Feature decisions

**Implement (Wave 4):** WP-43 (single-quote strings), WP-44 (pre-ENABLE
registerSymbol + inert-script demotion), WP-45 (dedupe/offsets/
dropdown/indirection), WP-46 (UDS + Lua-literal provides + one-shot
handover), WP-47 (allocation-only engine enable), WP-48 (luaCall
static provision), WP-51 (Lua-assembled program admission), WP-52
(broker surface), WP-53 (OS hotkeys), WP-49/50/54/57 (after design gates),
WP-55 (AOB multi-match → first match, CE parity) and WP-56 (record-Lua
CE-global stubs) from the Sinking City 2 field case (§3.9).

**Blocked-keep (documented):** dropdown choice > value width (30),
string `ShowAsHex` byte view (12, GC-A6 decision), `createThread`/
`threadWait` gate (2, AP-11), RE2 custom types (6, AP-08.7),
wildcard+external cleanup (3, Wave B2 guard), global-init residuals
(4), ASCII symbol violations (7), degenerate addressless trees (10),
managed method bare addresses (13, AP-11 live backend), authoring
bugs/singleton edges (per-case backlog, ~30).

## 6. Anonymized case derivation plan

Each fix produces synthetic `.ct` files under `TableReferences/`
(module token `ct2synthNN.exe`, SHA-256 pinned in
`tools/corpus_denominator/__main__.py`, `case-NN.ct` template style):

| Case | Origin shape (anonymized) | Covers |
| --- | --- | --- |
| case-26 | Requiem-style: single-quote `db` string, 3-arg `alloc` with `$process`, multi-token `label`/`registersymbol`, pre-`[ENABLE]` `registerSymbol`, `unregistersymbol(*)` + `deAlloc`, pointer-chain label definitions, consumer value records | WP-43, WP-44 |
| case-27 | Innocence-style: two alternative provider records (same symbol, different patterns) + consumer values; UDS `SymbolEntry` base + UDS/script conflict records | WP-45, WP-46 |
| case-28 | P3Reload-style: record-Lua `createMemScan`/`firstScan`/`waitTillDone`/`Result`/`registerSymbol("name", expr)` one-shot provider + consumers | WP-46b, WP-52 |
| case-29 | Ace7-style: inert credits script (comments-only ENABLE), group-heading hotkey (`moHideChildren` + `<Hotkey>`) | WP-44 (inert), WP-53 |
| case-30 | AtomicHeart-style: interdependent pointer-script providers (cycle) + UDS-defined base + consumer children | WP-46 (UDS), WP-49 |

## 7. Wave-4 execution plan

### Batch 1 (two parallel lanes)

| Lane | WPs | Modules | Expected unblock |
| --- | --- | --- | ---: |
| **w4-a** | WP-43 + WP-44 | `aa.py` (`_data_bytes`), `aa_program.py` (`_data_values`, `_literal_data`, preamble gate, no-action gate), small `compiler.py` policy hunk for inert demotion | ~16 direct + ~400 cascade |
| **w4-b** | WP-46 (UDS) + empty-section warning suppression | `table.py` (UDS parsing + section collection), `compiler.py` (provider map + warning), `address_expression.py` | 49 direct + cascades |

### Batch 2

| Lane | WPs | Modules | Expected unblock |
| --- | --- | --- | ---: |
| **w4-c** | WP-47 (allocation-only engine enable) + WP-55 (AOB first-match) | `hooks.py`, `engine.py`, `aa_program.py` (`link_program`), `memory.py` (`scan_module`) | runtime + 1 direct (Sinking City 2 Inf Health) |
| **w4-d** | WP-45 (dedupe/offsets/dropdown/indirection) + WP-56 (record-Lua CE-global stubs) | `compiler.py` cluster, `lua_host.py`, `lua_activation.py` | ~470 direct + runtime (Sinking City 2 ids 198/200/231) |

### Batch 3

| Lane | WPs | Modules | Expected unblock |
| --- | --- | --- | ---: |
| **w4-e** | WP-51 (Lua-assembled admission) + WP-48 (luaCall provision) | `compiler.py`, `aa_program.py`, `lua_program.py` | ~412 (DS2) + re2 share |
| **w4-f** | WP-52 (broker surface) | `lua_host.py` | runtime correctness (no plan change) |

### Batch 4 (design gates first)

WP-49 (cycle resolution — fixpoint/lazy design note), WP-50 (dynamic
script-parent providers — WP-38 contract extension), WP-53 (OS
hotkey capture — `RegisterHotKey`/`WM_HOTKEY`), WP-54 (table-Lua
phase 2 — scheduler + symbol-write lifecycle).

### Backlog / blocked-keep

`createthread`/`threadwait` (AP-11), RE2 custom types (AP-08.7),
string `ShowAsHex` (GC-A6), embedded Forms (WP-42, separate
milestone), managed method live resolution (AP-11), real-target
evidence (GOAL-4/5, AP-11), per-case singleton backlog.
