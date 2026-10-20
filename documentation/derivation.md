# CT2Trainer derivation and design intent

Status: October 20, 2026 (0.16; current corpus run `w4b4-case30-20261020081722Z`).

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

The measurement corpus (`TableReferences/`) is a synthetic clean-room corpus
that exercises the in-scope gap classes, so no third-party game table bytes
enter distributable tests. It contains 30 pinned synthetic tables. The full
case-to-origin mapping is documented in `TableReferences/README.md`; the
native tests embed only synthetic corpus content. These tables are not the
full real reference corpus and do not establish that every real table is
supported.

## 3. Current denominator and measurement baseline

- The current pinned synthetic corpus contains **30 tables and 6,143 expected
  actions** (records minus navigation; 1,291 groups counted separately), run
  `w4b4-case30-20261020081722Z`. Status split: 5,559 locked, 544 statically
  assumed, 42 unknown; 4 group-toggle actions.
- The feature matrix covers **42/42 in-scope features** (100% feature-weighted;
  7,475/7,475 action-weighted). This is coverage against the pinned synthetic
  corpus and is not full support for the real reference corpus. The separate
  full-corpus static catalog status is **2,698 of 117,624 plan entries blocked**.
- AP-11 remains separate: **0 of 6,143 expected actions** have confirmed real
  game effect. The metric excludes synthetic fixture/mock evidence.
- The three proof gates are closed with tested evidence: per-table completeness
  (`tests/test_native_table_completeness.py`), source-to-frozen parity and the
  binary IL2CPP adapter (`tests/test_native_source_frozen_parity.py` and
  `tests/test_native_il2cpp_static_probe.py`), and reproducibility
  (`tests/test_native_repro_chain.py`). Runtime acceptance remains
  `runtime_unverified: true` until Windows and Steam Deck/Proton acceptance is
  recorded.

Historical baseline: the October 10, 2026 `repo-reproducible` snapshot covered
13 tables / 5,967 actions and 39/39 features. The October 11 WP-14 snapshot
covered 14 tables / 6,011 actions. Those figures are retained in old run
artifacts and are not current measurements.
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
