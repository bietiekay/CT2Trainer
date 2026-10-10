# CT2Trainer Changelog

Single maintained changelog for CT2Trainer releases.

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
  `native-20261010T165731Z-3d1da645` via `scripts/Build-Native.ps1`:
  in-build suite 2617 OK / 25 regular skips; `ce_inputs` empty;
  `runtime_unverified` deliberately kept per gate.
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
