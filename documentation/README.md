# Documentation index

Status: October 10, 2026 (0.9.0-rc2). These files are the permanent project
documentation for humans and further agents. All documents refer to the
**Native edition** (CE-free, independent implementation). All documentation
is maintained in English.

## Getting started

- [Build guide](build.md): requirements, the single build entry point, the native test suite and release content rules.
- [Usage guide](usage.md): required inputs, saved-toggle behavior, table loading semantics and acceptance boundaries.
- [Derivation and design intent](derivation.md): clean-room rationale, measurement baseline, corpus and naming/format constants.
- [Native runtime and boundaries](native-runtime.md): CE-free implementation, redistribution assessment, implemented behavior and limits.
- [Native verification](native-verification.md): current verification baseline, reproduction commands and open gates.
- [Semantic corpus denominator](native-semantic-denominator.md): the 13 pinned case tables, gap classes and coverage.
- [../TableReferences/README.md](../TableReferences/README.md): synthetic clean-room corpus and the case-to-origin mapping.

## Tests and protocols

- [../tests/deck/compatibility-matrix.md](../tests/deck/compatibility-matrix.md): open Proton/Deck protocol for prefix, process effect and touch in both modes.
- [../tests/windows/fixture_target/README.md](../tests/windows/fixture_target/README.md): own C test target for the Windows function gates.
