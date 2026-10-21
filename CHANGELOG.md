# CT2Trainer Changelog

Single maintained changelog for CT2Trainer releases.

## 0.16 (2026-10-20)

- Wave 4 reference-corpus closure features (all W4 lanes integrated in
  the `native-0.16` cycle, merged into `main`; corpus cases 26…31
  pinned, gate:1 → 30 tables):
  - AA / table grammar (WP-43/44/45/46): single-quoted string data
    literals (both dialects, shared literal path); pre-`[ENABLE]`
    `registerSymbol` + inert comments-only scripts demoted to
    supported no-action; selection-aware provider dedupe, decimal and
    signed `<Offset>` values, missing dropdown-link demotion,
    indirection bound 2 → 6; `<UserdefinedSymbols>` interpretation
    (table-level static symbols, hex-only fail-closed, script
    providers keep winning) + empty-section warning suppression; Lua
    literal `registerSymbol` provides extraction + one-shot provider
    handover (release-on-detach at owner-scope retirement).
  - Symbol cycles and dynamic providers (WP-48/49/50): self-provision
    exclusion in the compiler dependency pass (a record's own
    registration satisfies its own reference; true cross-record
    cycles stay fail-closed with the exact reason); dynamic
    script-parent address providers (record-Lua `AddressList`
    providers with the `address_provider {provider_id, symbol: null}`
    marker, bounded static extraction, engine `dynamic_addresses`
    state); `luaCall(lua_aobscan(…))` / Lua-internal static symbol
    provision.
  - Engine / runtime (WP-47/51/52/55/56): allocation-only engine
    enable (no game write, symbol-only publish); Lua-assembled AA
    program admission at plan level (provable `autoAssemble` call);
    Lua broker scan/utility surface (`memscan.Result`/`OnlyOneResult`,
    `firstScan` nil rounding, found-list `getCount()`/`getAddress(i)`,
    `createStringlist`); AOB multi-match → first (lowest-address)
    match semantics per the CE `aobscan` family + match count/offsets
    in the debug log; record-Lua CE-global stubs (`OpenProcess` no-op
    success, `syntaxcheck` false, `ShellExecute` safe stub, no-op
    menu surface, named refusal for remaining missing globals).
  - Hotkeys and table-Lua phase 2 (WP-53/54): Windows OS hotkey
    capture bridge (message-only window, `RegisterHotKey`/`WM_HOTKEY`
    → queue, named refusal + programmatic-only fallback) +
    group-heading hotkeys (plain `moHideChildren` headings toggle
    their own applied state without child propagation, flagged groups
    cascade via the parent-activation path); persistent table-scope
    `createTimer` (record replay scheduler-free via inert stubs),
    table-scoped `registerSymbol` via `TableSymbolOwner` into plan
    field `table_lua_symbols` (supported record providers always
    win), consumer resolution through table symbols without
    `dependency_ids`, inverted teardown (table scope retires last,
    symbols released exactly once), UDS reseed on every confirmed
    attach.
  - Placeholder-token AOB (WP-57): `s1`/`s1.2` 2-byte tokens treated
    as wildcard displacements with the matched bytes captured at link
    time and persisted for the `[DISABLE]` restore; external region
    symbols get a named fail-closed reason.
  - Trainer UI (WP-58): compact touch-first row grid (canvas list,
    64/72 px rows, pill toggle + full-row tap, group sections
    replacing breadcrumb drill-down, inline value editor, state
    accent + transient reaction feedback); plan output byte-stable.
- Pinned corpus: cases 26/27/31 (W4 B1–B3) and 28/29/30 (W4 B4) pinned
  as the 25th–30th tables; chain `w4b4-case30-20261020081722Z`: 30
  tables, 6145 records, 6143 expected actions, feature matrix 42/42
  in-scope, weights 7475/7475.
- Reference corpus (local-only assessment, not shipped): catalog
  re-run post W4 B4 2,698 / 117,624 blocked (−934 vs post B1–B3).
- Post-release field fixes (2026-10-20 re-cut, from user testing of the
  first 0.16 build):
  - WP-58 UI startup crash: `TrainerWindow._button` hard-coded
    `font=`/`height=`/`pady=` on top of the `**style` spread, so the
    filter-chip call (height+font overrides) raised
    `TypeError: tkinter.Button() got multiple values for keyword
    argument 'height'` — every generated trainer crashed at startup.
    The defaults now live in the style dict so caller kwargs override
    them; a second latent WP-58 regression (pagination buttons passing
    the tuple `padx=(0, 4)` as a widget option, TclError "bad screen
    distance") moved the padding to `.pack()`. Regression test with
    real tkinter widget construction for every call-site signature:
    `tests/test_native_ui_button.py`.
  - Sinking City 2 field case (the "1 Activate me! Attach game's
    process" step and the multi-step pointer activation): the
    `OpenProcess` attach call runs as the WP-56 identity no-op; the
    chain (one-shot attach record → multi-match AOB pointer provider
    with `registersymbol` → staged pointer value record) now has
    end-to-end runtime proof on owned fake memory with the real Lua
    host — first-match scan resolution, symbol registration, byte-exact
    patch restore, the named staged gate, hex pointer-offset chase, and
    the named refusal for a process-name mismatch:
    `tests/test_native_sc2_attach_chain.py`. Field note: if a record
    fails at runtime with "pattern not found", the table's AOB pattern
    is missing from the installed game build (table/build mismatch —
    fail-closed by design, cf. the 2026-10-18 Sinking City 2 analysis).
  - State-lock self-repair and reliable restart (2026-10-21, user
    testing of the 0.16 re-cut, Sinking City 2): a target exit racing a
    hook-receipt read (Win32 299) blocked the engine; `close()` then
    refused permanently on the block flag and orphaned `state.lock`
    (the atexit net could not release it while a process session
    remained), so the trainer could not be restarted ("state.lock
    already exists"). Fixes in `src/ct2trainer/native/engine.py`:
    (1) `close()` now completes the exit cleanup when blocked but the
    target is gone — saved wishes survive in `state.json`; a
    still-alive target keeps the fail-closed refusal; (2) the atexit
    net releases the session and the lock when the target is provably
    gone; (3) the stale-lock startup probe retries a transient
    "unknown" owner observation once and, when the owner is proven dead
    but the full assessment is not eligible (most commonly: the
    previous session's target is still running), surfaces the concrete
    assessment reasons in an actionable refusal instead of the generic
    "delete that folder" line. Regression tests:
    `tests/test_native_stale_lock_selfheal.py` (7 tests) plus the
    updated never-attached-variant close assertion in
    `tests/test_native_engine.py`. Field note: the one non-working
    cheat in the field log (Inf Items, record id 15) is a table/build
    mismatch — the AOB pattern is absent from the installed build
    (ScanMiss logged twice), fail-closed by design, no code fix.

## 0.15 (2026-10-18)

- Prefix-cut byte-patch validation (field fix from the 0.14-ext2 Great
  Circle debug log, `d15268a`): the Stealth Mode and No Reload (2nd hook)
  entries use the classic byte-patch technique `db 90 E9` over a 6-byte
  conditional jump (je/jae rel32), reusing the original displacement to
  form `nop; jmp rel32`. Stage-time validation only accepted entry
  patches whose recorded original bytes AND whose patch bytes each decode
  as complete instruction sequences, so both halves of the legitimate
  prefix patch were rejected ("Entry patch cuts or contains an invalid
  instruction.") and the entries silently failed on attach.
  - `aa_program.link_program` now proves a prefix cut against the live
    target at link time: the recorded original must fail the
    complete-sequence check, the first original instruction boundary at
    or past the patch length must resolve inside a live window, and the
    patched prefix plus the original tail up to that boundary must decode
    as complete, valid instructions with no call/interrupt hazards.
    Passing blocks carry a `prefix_cut: true` flag.
  - `hooks._normalize` keeps the historical strict complete-instruction
    contract for every block; only blocks flagged `prefix_cut` at link
    time get the live re-verification (window read, head-byte match
    against the recorded original, boundary resolution, post-patch
    decode, control-flow safety) and fail closed on unreadable targets.
- Wave 3 reference-corpus closure features (trainer/converter):
  - Per-record hotkeys: source `<Hotkey>` bindings compile into plan
    metadata, register first-wins in the engine with deduplicated
    warnings, dispatch value operations on value records, and show
    original-binding cards plus a table-wide conflict banner in the UI.
  - Trainer-creator per-table inspection: structured supported/blocked
    results with named per-record reasons and named per-file
    diagnostics in the conversion GUI.
  - Runtime dynamic address providers: a Lua provider registers exactly
    one symbol on enable; relative children resolve the runtime base per
    activation; static module-relative siblings keep the module binding.
  - Read-only table-Lua bootstrap: the table LuaScript top level executes
    exactly once per attach through a read-only broker; refused or failed
    bootstraps surface a named banner and dependent record scripts stay
    visibly inactive.
  - Lua-owned symbol handover: record-Lua registerSymbol pairs and
    allocation-only programs publish symbols in the per-table
    `external_owned_providers` map; consumers carry explicit
    dependencies on their owning record, and the engine enforces the
    teardown order (owner deactivation only after consumers, exactly-once
    symbol release).
- Pinned reference corpus: 24 tables, 6,100 expected AP-11 actions
  (7,426/7,426 action-weighted feature coverage).
- Release build 0.15: run `native-20261018T055505Z-39f20180` cut from
  `main` @ `ed0b97b` via `scripts/Build-Native.ps1` (2026-10-18); in-build
  suite 3057 OK / 25 regular skips, `ce_inputs: []`,
  `runtime_unverified` deliberately kept per gate; source ZIP
  `CT2Trainer-0.15-source.zip` sha256
  `5d5a85f63f0b0948b05e06bfba8f40fa91e7bf75e5d981da22b33a3a5f522581`,
  portable ZIP `CT2Trainer-0.15-windows-portable.zip` sha256
  `cfcc8e06f65d0b3c6ec1ef4671f2be520c45c1c6c85572f1dbe6e69d15ea8414`.
  Both ZIPs ship the elaborated release READMEs and this changelog.

## 0.14 (2026-10-17)

- Per-wish restore isolation: a scan miss in one saved record no longer
  blocks the whole trainer (field finding from the 0.13 debug log: a stale
  AOB pattern in one record fell into the restore loop's catch-all
  exception path and blocked the engine, making every other saved toggle
  unusable until the process restart):
  - New `ScanMiss(ProcessMemoryError)` in `memory.py` for definite
    scan-result failures (pattern not found, ambiguous match, module
    changed while scanning, module-inventory or scan-quota bounds);
    process-level errors (identity change, inventory progress anomalies,
    read/write failures) stay plain `ProcessMemoryError` and still
    fail-close.
  - The engine's saved-wish restore loop now isolates each wish: a
    `ScanMiss` or `NativeRuntimeError` from one record fails that record
    only (logged as `restore-failed` with identifier and label, recorded
    in `entry_errors`) and the remaining saved wishes keep restoring;
    the engine stays connected and usable. A `StateError`/`PatchConflict`
    that already blocked the engine stops the loop; `RetryableAction`
    keeps the outer "waiting for a safe data-write point" handling.
- Debug logging now covers program (AA script) preflight scans, which
  previously bypassed the byte-patch `_operations` scan events:
  - `preflight_program()` accepts an optional `on_scan` callback; every
    `scan` / `scan_process` / `scan_region` op reports its symbol,
    module, pattern and resolved address, or the exception on failure.
  - `_install_program` logs `scan` / `scan-failed` events with
    `entry_id`, symbol, module, pattern, address and (while logging is
    enabled) module base / size / RVA; failures carry the full
    traceback. Byte-patch scan events in `_operations` now include
    `entry_id` as well.
- New tests: 2 restore-isolation tests in `tests/test_native_engine.py`
  (stale anchor fails only the affected wishes; an independent later wish
  still restores), 2 `on_scan` callback tests in
  `tests/test_native_aa_directive_wiring.py`, and a `ScanMiss`
  classification test in `tests/test_native_memory.py`.
- Release build 0.14: run `native-20261017T115850Z-1ebb48b7` cut from
  `main` @ `fca6b06` via `scripts/Build-Native.ps1` (2026-10-17); in-build
  suite 2932 OK / 25 regular skips, `ce_inputs: []`,
  `runtime_unverified` deliberately kept per gate; source ZIP
  `CT2Trainer-0.14-source.zip` sha256
  `a5b075cf6535c5eef3807da7b7b9429dda08a3cf9f9dba6fdafb879e0dfce0a9`,
  portable ZIP `CT2Trainer-0.14-windows-portable.zip` sha256
  `e57fe9b9fb56ef7a97f81a98f04455976c4b5e9ebddee655b24cbb64e7ed3103`.
  Both ZIPs ship the elaborated release READMEs and this changelog.

## 0.13 (2026-10-16)

- Optional runtime debug logging for generated trainers (user-requested
  feature for diagnosing red/disabled toggles on real tables):
  - New converter option **Debug logging** — checkbox in the converter
    GUI, `--debug-log` flag on the source CLI `inspect`/`prepare`/`build`.
    It sets the plan flag `debug_log: true` (default plans are
    byte-identical to before; the plan identity / trainer ID is
    unaffected, so state directories stay shared).
  - When enabled, the generated Trainer.exe appends one JSON line per
    runtime event to `<TrainerName>.ct2debug.log` next to the EXE (source
    runtime: `ct2trainer-debug.log` in the working directory): plan
    identity header, engine init + saved wishes, attach attempts and
    refusals (process not found, architecture mismatch, session claim,
    call broker), confirmed attach (PID, target EXE path, pointer width,
    creation time), target exit, every AOB scan (symbol, module, pattern,
    module base, size, RVA; failures with full traceback), definitions,
    symbol register/unregister, byte asserts (expected vs. actual bytes on
    failure), planned and written patches (address, original, new bytes;
    refusals, write failures, rollback failures), toggle / value-write /
    freeze attempts with success and failure outcomes, wish replay on
    attach, state saves, auto-on requests, engine blocking, and
    clean/unclean close. Errors carry exception type, message and full
    traceback.
  - Attach-stage failures are logged once per distinct cause so the
    repeating 250 ms poll loop cannot flood the log; the signature clears
    on a confirmed attach, so a recurring cause is reported again.
  - Logging is best-effort and never changes trainer behavior; disabled
    plans (the default) write no file at all.
  - New module `src/ct2trainer/native/debug_log.py`; instrumentation in
    `engine.py` (init, poll/attach, `_operations`, `_write_transaction`,
    `_save`, `toggle`, `set_value`, `set_freeze`, `request_auto_on`,
    `clear_desired`, `_block`, `close`), `ui.py` (action failures,
    startup failures), `launcher.py` (startup failures); `memory.py`
    exposes the bound target's `image_path`.
  - New tests: `tests/test_native_debug_log.py` (15 tests: plan flag
    default/opt-in/typo validation + trainer-ID stability, log writer
    JSON-line format / error traceback capture / disabled no-op / close
    semantics, engine integration for attach failure incl. repeated-
    failure dedupe, scan failure, assert failure, state-save failure,
    full toggle/value/close cycle, and no-file-when-disabled).
- Module-snapshot robustness fix (surfaced in the field by the new debug
  logging): the target module inventory used by every AOB scan and by
  target-architecture re-verification now retries with the native-only
  TH32CS_SNAPMODULE flag when the combined native/WOW64 snapshot fails
  (observed in the field: Win32 error 299,
  ERROR_INVALID_STARTING_ADDRESS, on some Windows builds); if both
  attempts fail, the named error reports both attempts and the first
  Win32 code. Two new tests in `tests/test_native_architecture.py` pin
  the fallback and the double-failure error.
- Release build 0.13: run `native-20261016T190005Z-b3139b30` cut from
  `main` @ `d57e62c` via `scripts/Build-Native.ps1` (2026-10-16);
  in-build suite 2927 OK / 25 regular skips, `ce_inputs: []`,
  `runtime_unverified` deliberately kept per gate. Artifacts:
  `CT2Trainer-0.13-source.zip` (sha256
  `23b57307819e4262d8ca894ac16c86d595df9945c1afec25750f66bb9e0c9124`),
  `CT2Trainer-0.13-windows-portable.zip` (sha256
  `d7f64efbae975f477e5bb011796d64276f32ef4300d4a0986961e95ae63aca78`);
  superseded 0.13 run `native-20261016T181516Z-b8ae88de` (pre
  module-snapshot fallback, cut from `main` @ `7184547`).
  both ZIPs ship the elaborated release READMEs (the portable user
  guide now documents the debug-logging option) and this changelog.
  The build carries the released 0.12 content (Wave 2 corpus closure)
  unchanged; 0.13 adds the debug-logging option and the module-snapshot
  fallback only.

## 0.12 (2026-10-16)

- Wave 2 of the reference-corpus closure cycle on `native-0.12`
  (all ten work packages merged; full local suite 2910 OK / 25 expected
  skips, 0 failures):
  - W2-A (WP-27/32/33/34, lane `w2-a` @ `a49a1db`, merge `aa6371b`):
    - WP-27 profile-aware linked dropdowns: every choice validated
      against the record's own value type at compile time (per-choice
      named refusals: byte-array hex-byte width, bit-field range,
      integer type width); missing vs. ambiguous link targets split;
      engine validator delegates to the compiler refusal so both layers
      agree; reference dropdown family 1,215 → 0.
    - WP-32 addressless value-record demotion to supported
      non-actionable placeholder headings (`Addressless value record is
      a non-actionable table placeholder.`); relative-address children
      stay blocked; demoted placeholders excluded from the
      parent-activation cascade.
    - WP-33 IEEE-754 bit-pattern editing for hex Float/Double (exactly
      8/16 hex digits, optional `0x` prefix, little-endian raw bytes,
      `struct` round-trip proof shared by parse/format/dropdown/
      value-link layers); fixed-width policy shared across
      engine/compiler.
    - WP-34 diagnostics: `Dropdown link target is missing or
      ambiguous` split into per-name missing/ambiguous refusals;
      comma-decimal Float/Double choice normalization (FLAG-2
      follow-up); per-choice width-precision refusal names the
      offending choice; AP-08.3/08.7 citations aligned.
  - W2-C (WP-30/36, lane commit `e5c039e`, merge `32e0cdd`):
    - WP-30 bounded address-expression profile: typed casts are no-ops
      for symbol extraction, nested indirection up to depth 2, `@`
      forms accepted; the `requires == address symbols` match gate kept;
      malformed forms refused with named depth-limit reasons.
    - WP-36 `aobscan`/`aobscanregion` staged under the existing scan
      budget; `createThread()/threadWait()` keep the named fail-closed
      capability gate; 3-arg `globalalloc(sym,size,$process)` accepted
      in the global-init profile with shared symbol registration.
  - W2-B (WP-28/29/31/35, lane commit `d4d062d`, merge `2f68f80`):
    - WP-28 two-stage per-program label scoping: a program's own bare
      positional labels (`return:`, `endp:`) are local at the prepare
      level (`positional_labels`); the table compiler re-declares them
      as external requirements whenever another supported record
      provides the same symbol (registered symbols win over local label
      definitions); bare labels without a provider or an address anchor
      refused (`Positional label appears before any address cursor.`).
      P3Reload `return:` family unblocked; reference catalog P3Reload
      blocked 3,006 → 331.
    - WP-29 `alloc` in the data dialect + allocation-only
      initialization profile (no game write; `dealloc`/
      `unregistersymbol` on disable; no dead-allocation publication);
      one-shot programs stay refused (`Enable section has no
      executable patch or data.`).
    - WP-31 data-dialect grammar: 2-arg `dealloc`, multi-token
      `registersymbol` pre-pass, `registerlabel`, bounded no-op
      `fullaccess(addr,size)`, `/* */` comments, line-attached error
      messages; comment-only scripts classified `inert/documented`.
    - WP-35 operand-less `dq`/`resb` reservation spans as
      program-owned allocations (must be written before publish, no
      cross-program access); outside owned regions refused
      (`Uninitialized reservation (dq/resb) requires a program-owned
      allocation.`).
- Corpus: 20 pinned tables (was 19): case-16 part 2 refined and
  case-17 pinned as the 19th table (W2-A); case-15 part 2 refined and
  re-pinned — 21 records, cast/indirection records, chain
  `w2c-case15p2b-20261015144326Z` (W2-C); case-18 pinned as the 20th
  table — `ct2synth18.exe`, 18 records, IDs 10–27: 16 supported,
  IDs 26/27 deliberately kept blocked with named reasons (W2-B).
  gate:1 now covers all 20 pinned tables.
- Feature matrix stays 42/42 in-scope (100% feature-weighted,
  7408/7408 action-weighted over run `w2b-case18-20261016142912Z`);
  AP-11 campaign: 0/6,080 confirmed (separate end goal, excluded from
  the 100% feature metric).
- Reference catalog re-run (151 local-only tables, 143 distinct
  hashes): 110,047 supported (54,234 staged), 7,577 of 117,624 blocked
  (was 9,962 after W2-A); 1 whole-table compile error (SuperMeatBoy
  legacy binary).
- Release build 0.12: run `native-20261016T163910Z-d047f2d2` cut from
  `main` @ `ba1d3e4` via `scripts/Build-Native.ps1` (2026-10-16);
  in-build suite 2910 OK / 25 regular skips, `ce_inputs: []`,
  `runtime_unverified` deliberately kept per gate. Artifacts:
  `CT2Trainer-0.12-source.zip` (sha256
  `f5a5468da6e49ee5d4812dce3edea71e87e4bb9736ce4bf3486dfc0c66e70165`,
  12,811,693 bytes) and
  `CT2Trainer-0.12-windows-portable.zip` (sha256
  `7bd582e33f2978c641bb36a22ad8fc5f21bc9b695bb16930bed19720eaa81619`,
  28,313,477 bytes); EXEs: `CT2Trainer-Template.exe` (sha256
  `14c0d86726404087299a2e7e924cb3d960562671f7d9e2e174d8706992343edc`,
  14,516,772 bytes), `CT2Trainer-Converter.exe` (sha256
  `1ebbf708631fea59618c7d0c18e5de229a699e09678595977033bc7ac40307f5`,
  28,569,255 bytes). Both ZIPs ship the elaborated release READMEs
  (source: product overview + build guide; portable: full user guide)
  and this changelog (0.12 + retro 0.11 entries).

## 0.11 (2026-10-12)

- WP-15 (L2-37): fully-permitted executable bit-field writes routed
  through the engine (merge `d3316aa`; suite 2688).
- WP-16 (L5-19): named table-Lua tabs gathered into the table-Lua
  bootstrap source — main-body-only byte identity, document-order
  joining, fail-closed invalid-tab activation (merge `38a830d`;
  suite 2679).
- WP-17: build version in the converter and trainer window titles plus
  a clickable GitHub repository link in both windows; fail-closed
  `verify_version_sync` fails the build on VERSION/`__version__` drift
  (merge `557b2ac`; suite 2698).
- WP-18: `$process` AOB module token for `aobscanmodule` at both engine
  scan dispatch sites; trailing `@F` without explicit `@@` falls back
  to the next positioned named label (explicit `@@` still wins);
  PRAGMATA reference table 595/595 supported, 0 blocked (merge
  `9a76eb8`; suite 2710).
- Release build 0.11: run `native-20261012T092729Z-2d8aaf12` cut from
  `main` @ `9a76eb8` via `scripts/Build-Native.ps1` (2026-10-12);
  in-build suite 2710 OK / 25 regular skips, `ce_inputs: []`,
  `runtime_unverified` deliberately kept per gate. Artifacts:
  `CT2Trainer-0.11-source.zip` (sha256
  `168c14a452595588a6483140f1d43bec818d0f0d0e9eb72167453a80624469db`)
  and `CT2Trainer-0.11-windows-portable.zip` (sha256
  `8a2d6ac6f8b802714fe7578de54cea432506a41f8bf91d597a03fa086b04f196`).
  Superseded 0.11 run: `native-20261011T182033Z-f3317337` (pre-WP-18,
  in-build suite 2698/25).

## 0.10 (in cycle, 2026-10-11)

- WP-14 "Staged Capabilities" (PRAGMATA-class tables):
  - Signed pointer offsets: `<Offsets>` literals accept an explicit sign
    (`+28` = `0x28`, `+0x130`, `-0x10`); malformed forms
    (`++10`, `+`, `0x`, empty, trailing junk) stay rejected fail-closed.
  - Script-parent activation cascades: the tested flag-class contract
    (AP-07) extends from group headings to script records with children
    (`required_dependency` / `direct_activation` / `collective_off`);
    `moBindActivation` on any non-heading parent stays a visible named
    block; value parents with flags stay fail-closed (documented inert
    scope).
  - Staged runtime gating: records whose address needs a symbol provided
    by another supported record carry `staged` metadata; the engine gates
    read/write/freeze on provider liveness (named, fail-closed error while
    the provider is inactive; UI shows a pending state and auto-unlocks);
    provider OFF releases freeze on frozen staged children first, then
    deactivates the provider.
  - Record-ID activation sets: the converter statically extracts
    enable/disable ID sets from embedded `{$lua}` blocks
    (`getMemoryRecordByID(<int>)` + `Active = true|false`, uniform
    direction per section); such records route through the engine's
    dependency-ordered set application instead of executing the
    CE-coupled Lua. Plan validators re-derive `staged`/`activation_sets`
    and refuse tampered metadata.
  - Trainer/converter UI states: staged pending card, master-toggle card
    for activation sets, converter `Staged` capability column and
    `N supported (M staged, K blocked)` status line.
- Corpus: 14th pinned table `TableReferences/case-14.ct` (PRAGMATA
  behaviour derivative, `ct2synth14.exe`, 57 records: master toggle with
  record-ID activation set, script parents with all three flag classes,
  nested script provider/consumer, signed pointer offsets on record and
  heading, one-shot guarded write).
- Denominator: 14 pinned tables, 6011 expected actions (was 5967), three
  new gap labels (`signed_pointer_offset`, `script_parent_activation`,
  `record_activation_set`), 39 gap classes, 42 in-scope features
  (39 + 3 gates) all covered: 100% feature-weighted, 7361/7361
  action-weighted (was 7332/7332); all `gap_inventory/` artifacts
  regenerated byte-reproducible (run
  `wp14-staged-20261011T093320Z`, consistency `all_ok`).
- Old-13 plan stability: per-table plan diff rc2 → WP-14 shows
  12/13 byte-identical; the only delta is case-06 entry 17258 (async
  Lua/AA record) flipping blocked → supported — the Lua
  symbol-provider extraction resolves a table-owned symbol the old
  envelope check rejected (table totals: supported 38 → 39, blocked
  293 → 292).
- Classifier fidelity: `assert` added to the supported AA directive list
  (product-supported guard directive); ENABLE-only scripts with a
  guarded write classify as `one_shot` (mirroring the product's
  `compile_one_shot` contract) instead of `unknown`.
- PRAGMATA.CT reference measurement (reference input only, never in the
  repo): 595 records → 586 supported (416 staged / 170 non-staged),
  9 blocked (2 records with a strict `"$process"` address plus an
  anonymous assembly label; 7 `i_base_*` children without a unique
  supported provider — each individually justified).
- Release build 0.10: run `native-20261011T121914Z-bfc5fc11` cut from
  `main` @ `64b1e63` via `scripts/Build-Native.ps1` (2026-10-11);
  in-build suite 2671 OK / 25 regular skips, `ce_inputs: []`,
  `runtime_unverified` deliberately kept per gate, source inputs
  unchanged. Artifacts: `CT2Trainer-0.10-source.zip` (sha256
  `93f1f353abaf399287ebf27b90dcb794793658cd6663a6fc68d25998e5f2eb83`,
  12,729,937 bytes) and `CT2Trainer-0.10-windows-portable.zip` (sha256
  `833441069b078d352a556d650ccb7ddbbc8604aacc6e752adfd869d8b11f36f1`,
  28,231,325 bytes); EXEs: `CT2Trainer-Template.exe` (sha256
  `1ae0d2163bac4271711f7a7e826346cd1513ce3b231563b9f64ddc0526f93c14`,
  14,475,270 bytes), `CT2Trainer-Converter.exe` (sha256
  `a8e3005ed6bc7c18092ac0fcd28e42495c0573e87abe4fb3e5f0f79c9094eb89`,
  28,490,774 bytes).

## 0.9.0-rc2 (2026-10-10)

- Clean-room synthetic CT corpus: `TableReferences/` is replaced by a
  synthetic clean-room corpus of the 13 pinned tables as neutral case
  files (`case-01.ct` through `case-13.ct`); own code only, no
  third-party copyrighted material in the corpus or the distributed
  releases. Affected tests are re-pinned to the synthetic corpus.
- CT2Trainer naming: the Native edition is officially CT2Trainer. Fresh
  builds produce `CT2Trainer-<version>-source.zip` and
  `CT2Trainer-<version>-windows-portable.zip`; the binary plan footer
  magic is `CT2NATV1` and the template stub marker `CT2BASE1` (both
  8 bytes). The one-shot marker magic `TFSH0001` is kept as a stable
  format constant.
- 0.9 feature set: 5967-action denominator baseline; 39/39 in-scope
  features covered (100% feature-weighted, 7332/7332 action-weighted).
  The 100% feature-matrix goal (excluding AP-11) is reached. AP-11
  (5967 expected actions, 0 confirmed so far) remains a separate end
  goal and is excluded from the 100% feature metric.
- Gates 1-3 closed with tested evidence (their action weights remain
  0; they are completeness/proof features, not record actions):
  - gate:1 per-table completeness for all 13 pinned tables
    (Forms, Lua lifecycle, Custom Types, Assets) is demonstrated by
    `tests/test_native_table_completeness.py` (every source record
    preserved, each table-level construct handled or surfaced
    fail-closed, plus a synthetic embedded-Files case).
  - gate:2 Source-to-Frozen parity of the 0.9 feature set is
    demonstrated by `tests/test_native_source_frozen_parity.py`
    (real corpus plans round-trip through build_trainer /
    read_embedded_plan byte-identical); the binary CLI/GUI adapter
    for the static IL2CPP parser is new: the frozen launcher exposes
    `--il2cpp-static-pe/--il2cpp-static-metadata/--il2cpp-static-report`
    and the source CLI exposes `ct2trainer native il2cpp`, both
    producing a bounded read-only report
    (`tests/test_native_il2cpp_static_probe.py`).
  - gate:3 end-to-end reproducibility chain across all features with
    exact commands and pinned inputs is demonstrated by
    `tests/test_native_repro_chain.py` (denominator -> feature matrix
    -> AP-11 manifest reproduced byte-for-byte for a fixed run-id).
- Portable frozen-build fix: `api-prototypes.json` is now bundled into
  the EXE and, in frozen mode, resolved against the bundle root
  (`sys._MEIPASS`), so trainer generation in the portable ZIP no longer
  fails on a missing `dependencies/native/mono-api-source/` path;
  `tests/test_native_mono_runtime.py` (`PinnedTablePathTests`) covers
  path resolution in both source and frozen mode.
- Fresh, fully offline build
  `native-20261010T172336Z-ffe35eb0` via `scripts/Build-Native.ps1`:
  in-build suite 2617 OK / 25 regular skips; `ce_inputs` empty;
  `api-prototypes.json` present in both EXE payload inventories;
  `runtime_unverified` deliberately kept per gate. The portable ZIP of
  this release was user-tested (converter run plus generated trainer on
  a machine without CE or Python).
- Release artifacts for this entry:
  `CT2Trainer-0.9.0-rc2-source.zip`,
  `CT2Trainer-0.9.0-rc2-windows-portable.zip` with the output hashes
  recorded in the build report.
- Release-archive hygiene: the source ZIP contains exactly the
  build-essential tree plus the build/usage/derivation docs, the
  runtime and verification docs, the Proton/Steam Deck compatibility
  matrix, the feature-matrix artifact, and this single changelog.
  Dev ledgers, plans and corpus scratch stay out of distributed
  releases; the build allowlist in `tools/native_build.py` is the
  single source of truth, verified by the in-build CE-content scan.
- 0.9.0-rc1 remains an earlier release; it is not superseded by this
  entry.

## 0.9.0-rc1 (2026-10-08)

- First release under the CT2Trainer name, built fully offline
  (`native-20261008T093705Z-61c2257d` via `scripts/Build-Native.ps1`):
  in-build suite 2595 OK / 25 regular skips, `ce_inputs` empty,
  `runtime_unverified` deliberately kept per gate.
- Release artifacts for this entry:
  `CT2Trainer-0.9.0-rc1-source.zip`,
  `CT2Trainer-0.9.0-rc1-windows-portable.zip` with the output hashes
  recorded in the build report.
- Binary plan footer magic `CT2NATV1` and template stub marker
  `CT2BASE1` introduced; the owned fixture corpus was re-pinned after
  the marker/schema change.
