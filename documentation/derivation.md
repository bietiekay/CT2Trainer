# CT2Trainer derivation and design intent

Status: October 10, 2026.

This document explains why the CT2Trainer Native edition exists, how it was
derived from the public Cheat Engine contract without using CE
implementation material, how the measurement baseline is defined, and how
the naming and format constants evolved. It is self-contained: it does not
cross-reference development ledgers.

## 1. Clean-room mandate

The Native edition is an **independently designed, source/binary-
redistributable converter and trainer**. It uses **no CE implementation
inputs or binaries at all** — no CE source, no CE build structure, no CE
DLLs, stubs, drivers, no patched Lua runtime, and no CE payload in any
output. Only the **public API and format contracts** (the published
`.CT`/XML table format, documented CE-Lua/AA behavior, public wiki
contracts such as the MemoryRecord semantics) are derived as the contract
to implement. Own test processes and tables serve as behavioral examples;
original tables are never executed during the audit.

All implementation, test and documentation content in this tree is either
independently authored or a byte-pinned, license-checked upstream
component. MIT/BSD third-party components (NASM, iced-x86,
Lupa/Lua, Python/Tcl/Tk, selected LibCpp2IL and Mono API sources) are
retained with their upstream pins, licenses and local-change evidence.
Distributed releases contain only allowlisted content; the build
allowlist in `tools/native_build.py` plus the in-build CE-content
scan enforce this.

## 2. Clean-room corpus (synthetic replacement of the real tables)

The measurement corpus (`TableReferences/`) is a **synthetic clean-room
corpus** that exercises the same 36 gap classes, so that no third-party
game table bytes enter the distributable tests. The 13 pinned tables are
committed as flat, neutral case files `case-01.ct` through `case-13.ct`;
the game of origin for each case is documentation-level provenance only
and is recorded in `TableReferences/README.md`:

1. `case-01.ct` (origin: Trine 2)
2. `case-02.ct` (origin: Fallout 4)
3. `case-03.ct` (origin: Yooka-Laylee)
4. `case-04.ct` (origin: Disco Elysium)
5. `case-05.ct` (origin: Alien Isolation)
6. `case-06.ct` (origin: Resident Evil 2)
7. `case-07.ct` (origin: Borderlands 3)
8. `case-08.ct` (origin: Clair Obscure Expedition 33)
9. `case-09.ct` (origin: Silent Hill Townfall, Steam build)
10. `case-10.ct` (origin: Senua's Saga Hellblade 2)
11. `case-11.ct` (origin: Red Dead Redemption 2)
12. `case-12.ct` (origin: Silent Hill Townfall, community "rml" build)
13. `case-13.ct` (origin: Resident Evil 4)

Each of the 13 tables carries **exactly one owned module token**,
`ct2synth01.exe` through `ct2synth13.exe`, assigned 1:1 to the pinned paths
in the order listed above (verified: every table references only its own
token, and no other module name appears in the corpus). The committed
baselines under `gap_inventory/` are regenerated against this synthetic
corpus (run `repo-reproducible`); the native tests embed only synthetic
corpus content.

## 3. Denominator and measurement baseline

- The pinned start corpus of **13 tables** contains **5,967 expected
  actions** (records minus navigation; groups counted separately). Status
  split at the baseline: 5,455 locked (91.4%) / 479 statically assumed
  (8.0%) / 33 unknown (0.6%); 1,269 groups; 0 group-toggle actions.
- The feature matrix (`gap_inventory/feature-coverage.json`, run
  `repo-reproducible`) measures **39/39 in-scope
  features covered: 100% feature-weighted and 7332/7332
  (100%) action-weighted**. The 100% feature-matrix goal (excluding
  AP-11) is reached and closed. The four
  AP-11 features (real game installs/builds, observed game effect,
  VM/Clean-PC, real Steam Deck with Proton prefix incl. physical input) are
  excluded from the metric by rule.
- The **AP-11 campaign** (the 5,967 expected actions with **0 confirmed**
  real game effect so far) is a **separate end goal** and is excluded from
  the 100% feature metric.
- The three **gate features** are now closed with tested evidence:
  gate:1 per-table completeness (Forms, table-Lua lifecycle, Custom Types,
  Assets) demonstrated by `tests/test_native_table_completeness.py`;
  gate:2 Source-to-Frozen parity of the 0.9 feature set including the
  binary CLI/GUI adapter for the static IL2CPP parser demonstrated by
  `tests/test_native_source_frozen_parity.py` and
  `tests/test_native_il2cpp_static_probe.py`;
  gate:3 the end-to-end reproducibility chain with exact commands and
  pinned inputs demonstrated by `tests/test_native_repro_chain.py`.
  Gate action weights remain 0 (completeness/proof features, not record
  actions).

## 4. The 36 gap classes (concept)

Gap classes are **static, read-only classifications of table
constructs** — values (numeric writes, freeze, arrays, bitfields, empty
address forms), strings (encoding, codepage, dropdown links), AA scripts
(directives, scans, alloc/globalalloc, thread control, protection control,
debugger API, nested scripts, conditional blocks, incomplete ENABLE/DISABLE
sections, unverified residual tokens), Lua hosts (host profile, record
bodies, managed runtime access, typed target calls, worker threads, GUI
API, process API, symbol API, CE engine API, debugger API, clock/speed,
dynamic autoAssemble), custom type codecs, group/parent activation and
recursive parent values, cross-record symbol resolution, and the one-shot
save contract.

A gap-class assignment is a **syntax assumption, never a behavioral
proof**: it says only that a record statically requires the capability the
class names. Statuses are `statically_assumed` (structurally plausible
only), `locked` (requires a concretely missing API/feature) or `unknown`
(unknown, and never reinterpreted as success). Fixture/mock evidence is
synthetic and does not count as game effect; real observed game effect is
measured exclusively by the Windows/Deck test lanes. The synthetic corpus
is designed so that **every in-scope gap class is exercised**, and each
gap class keeps an in-machine static/fixture verification path.

## 5. Naming and format constants

- The project is **CT2Trainer** (CT -> Trainer). All current code,
  configuration, documentation and tooling use this name; all repository
  content is English-only.
- The **binary plan footer magic** is `CT2NATV1` (8 bytes) and the
  **template stub marker** is `CT2BASE1` (8 bytes) — both part of the
  hash-bound template/plan format.
- `TFSH0001` (the one-shot marker magic in `oneshot.json`) is
  **intentionally kept as a stable format constant**: renaming it would
  break existing per-user state. It is documented, not naming debt.
- Fresh builds are named `CT2Trainer-<version>-source.zip` and
  `CT2Trainer-<version>-windows-portable.zip`, where `<version>` is the
  content of the root `VERSION` file.
