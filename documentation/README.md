# Documentation index

Status: October 20, 2026 (0.16; current release build `native-20261020T150115Z-c426fb92`). These files are the permanent project
documentation for humans and further agents. All documents refer to the
**Native edition** (CE-free, independent implementation). All documentation
is maintained in English.

## Getting started

- [CE trainer-behavior parity assessment](ce-feature-parity-assessment.md):
  current capability map and reproducible method for measuring the original
  reference tables against the CE 7.5 behavior contract, excluding purely
  visual UI work.

- [Build guide](build.md): requirements, the single build entry point, the native test suite and release content rules.
- [Usage guide](usage.md): required inputs, saved-toggle behavior, table loading semantics and acceptance boundaries.
- [Derivation and design intent](derivation.md): clean-room rationale, measurement baseline, corpus and naming/format constants.
- [Native runtime and boundaries](native-runtime.md): CE-free implementation, redistribution assessment, implemented behavior and limits.
- [Native verification](native-verification.md): current verification baseline, reproduction commands and open gates.
- [Semantic corpus denominator](native-semantic-denominator.md): the current 30 pinned synthetic tables, gap classes and measured coverage.
- [../TableReferences/README.md](../TableReferences/README.md): synthetic clean-room corpus and the case-to-origin mapping.

## Agent workflow

- [Native progress ledger](native-progress.md): confirmed state, measured
  numbers and the prioritized open work (binding result list, referenced by
  `AGENTS.md` and the continuation plan).
- [AP-11 game campaign](native-ap11-campaign.md): the real-game campaign
  manifest, per-table procedure, report format and ingestion tooling.
- [Subagent lane rules](subagent-lane-rules.md): the operational contract
  for parallel implementation lanes (workspace, tests, reporting).
- [New table candidates](native-new-table-candidates.md): historical
  corpus-selection rationale behind the pinned case tables.

## Tests and protocols

- [../tests/deck/compatibility-matrix.md](../tests/deck/compatibility-matrix.md): open Proton/Deck protocol for prefix, process effect and touch in both modes.
- [../tests/windows/fixture_target/README.md](../tests/windows/fixture_target/README.md): own C test target for the Windows function gates.
