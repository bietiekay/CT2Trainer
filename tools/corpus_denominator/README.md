# corpus_denominator

Self-contained, stdlib-only AP-10 corpus denominator tool for CT2Trainer
Native. It builds a deterministic, read-only static inventory and gap report
for a Cheat Engine `.CT` corpus: 13 pinned start tables plus the remaining
corpus. CT Lua/AA bodies are never executed; everything is static token
classification and explicitly marked syntax assumption.

## Usage

Python 3.12, standard library only (no third-party packages, no build steps):

```powershell
python tools\corpus_denominator\__main__.py `
    --corpus <corpus-root> `
    --output <out-dir> `
    [--run-id <id>]
```

- `--corpus` (required): directory containing the `.CT` corpus, searched
  recursively. The corpus is strictly read-only; the tool refuses to write
  into it or above it.
- `--output` (required): directory that receives exactly two files,
  `inventory.json` and `gap-report.json` (created if missing).
- `--run-id` (optional, default `repo-reproducible`): carried verbatim in the
  `run_id` and `generated` fields (`"run <run-id>"`).

Example (repo layout):

```powershell
python tools\corpus_denominator\__main__.py `
    --corpus TableReferences `
    --output <out-dir> `
    --run-id repo-reproducible
```

Running `python -m tools.corpus_denominator ...` from the repo root with the
same flags produces identical artifacts.

## Output schema

Both artifacts use the same schema and top-level keys as the committed
reference artifacts `gap_inventory/inventory.json` and
`gap_inventory/gap-report.json` (see
`tools/corpus_denominator/__init__.py` `SCHEMA_NAME`,
`corpus-denominator/v1`). JSON is written with sorted keys, 1-space indent,
`ensure_ascii=False` and a trailing newline.

Deterministic: same corpus + same run-id => byte-identical output (stable
SHA-256). There are no wall-clock timestamps; the only run-specific field is
the documented `generated` run stamp (and the matching `run_id`), which the
committed reference artifacts fill with `repo-reproducible`.

`inventory.json` verifies the six byte-pinned reference tables from
`tests/fixtures/reference-inventory.json` (hash + CheatEntry count per file)
in its `reference_verification` section; the repo root is derived from the
package location (`<repo>/tools/corpus_denominator/`), so the fixture path is
`<repo>/tests/fixtures/reference-inventory.json`.

## Provenance

Ported (classification logic byte-faithful; only imports adjusted to
package form, no logic changes) from an early development run on
2026-10-02:

| Source file (SHA-256) | Ported to |
| --- | --- |
| `corpus_lib.py` `1F160F68956B557DB04D2EEA06158DCCB79E0770028512C21A16EE2E93149489` | `lib.py` |
| `corpus_scan.py` `B53677AE0B403B13C6A1995E2D2165C02FC2A1479462FE4B8A9E6F81D4EBE7E6` | `scan.py` |
| `corpus_classify.py` `5CBE1BB3DF57500AE04ABEDBB69F2BABC726206A1FE7F3F6D531DE37F9E67CE2` | `classify.py` |
| `corpus_table.py` `FBDD0E63129C3B7CEEA6653D9B94059A9D5D87A0AD5CA37368910CDECB96748D` | `table.py` |
| `build_reports.py` `002E62108049A4A3021F8A8A63BA7D3F68F620245102E621FBF1012C62156525` | `__main__.py` |

Adaptations in `__main__.py` (documented, no classification-logic changes):
hardcoded `WORK`/`ROOT`/`REPO`/`OUT_DIR`/`RUN_ID` replaced by the CLI
parameters above; `generated` changed from a hardcoded run-date stamp to the
deterministic `"run <run-id>"`; `corpus_root` normalized via
`os.path.normpath`; import block made package-compatible with a direct-script
fallback.

## Limits

- The shipped `.CT` corpus (`TableReferences/`, 13 synthetic case tables,
  see `TableReferences/README.md`) is read-only test input;
  `tests/fixtures/reference-inventory.json` additionally pins six of the
  tables byte-exactly.
- Static syntax assumptions only: no attach proof, no CE/Windows runtime
  gate, no game-effect evidence. `confirmed_game_effect_actions` stays `0`.
- The 13 pinned start tables are part of the tool's contract
  (`PINNED` in `__main__.py`); a missing pinned path fails the run.
- The `generated` field carries the run-id stamp, not a wall-clock time;
  the committed reference artifacts use `repo-reproducible`.
