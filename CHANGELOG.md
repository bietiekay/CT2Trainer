# CT2Trainer Changelog

Single maintained changelog for CT2Trainer releases.

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
- Release build 0.12: cut from `main` via `scripts/Build-Native.ps1`
  (2026-10-16); in-build suite 2910 OK / 25 regular skips,
  `ce_inputs: []`, `runtime_unverified` deliberately kept per gate.
  Artifacts: `CT2Trainer-0.12-source.zip` and
  `CT2Trainer-0.12-windows-portable.zip` (per-run sha256 values in the
  run folder's `build.json`, recorded in
  `documentation/native-verification.md`).

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
