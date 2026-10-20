# CT2Trainer: AP-11 Game Campaign Plan and Report Ingestion

Status: **2026-10-20 current manifest** — 30 pinned synthetic tables,
6,143 expected actions, 0 confirmed real-game effects (run
`w4b4-case30-20261020081722Z`; `gap_inventory/ap11-campaign.json`). The
feature matrix is complete at 42/42 and 7,475/7,475 action-weighted;
AP-11 remains a separate open goal. The 13-table/5,967-action plan and
its older run-specific details below are historical snapshots, retained
for audit context; the committed manifest is authoritative for current
counts. Wave 4 is complete and the 0.16 field-fix re-cut is recorded in
[`plans/TRACKING.md`](../plans/TRACKING.md). The next reference-corpus
work is tracked in the
[reference-table roadmap](../plans/reference-table-100-roadmap.md).

AP-11 (real-game confirmation) runs on the user's machine. This runbook
prepares it here: an executable, deterministic campaign plan over the
pinned synthetic corpus, plus a validating report tool for the later
real-game observations. This lane touches no game and no process: everything here is
static analysis of committed artifacts and read-only CT bytes under
`TableReferences/` (bytes are hashed and tokenized for process-name
candidates only). No CE implementation inputs or binaries are used.

## Files

| File | Role |
| --- | --- |
| `tools/corpus_denominator/ap11_campaign.py` | CLI, subcommands `manifest` (default) and `report`; stdlib only; conventions identical to `feature_matrix.py` / `gap_traceability.py` |
| `gap_inventory/ap11-campaign.json` | committed manifest baseline, generated with run id `repo-reproducible` (byte-identical on rerun with the same run id; see `test_committed_manifest_is_byte_reproducible`); refreshed for the synthetic corpus under run `wpB-cleanroom4-20261010T104008Z` |
| `tests/test_native_ap11_campaign.py` | 28 focused tests (manifest determinism, consistency, integrity, refusal; report validation, dedup, replacement, state binding) |
| `build/runs/` | local run evidence (suite logs, regeneration outputs); gitignored, not part of the repository or distributed releases |

## Campaign manifest (`ap11-campaign/v1`)

One entry per pinned table, in gap-report order. Each table carries
`name`, `ct_path`, `ct_sha256`, `architecture`, `process_candidates`
(owned `process_detect.find_candidates` over the actual CT bytes),
`expected_actions`, `category_counts`, `priority_order`, and `records`
— a map of `str(record_id)` to the record's static category, so the
report path can validate observations without the gap report.

Priority convention: fixed category order
`value_freeze, string_write, one_shot, persistent_script, custom_value`;
per-table `priority_order` is that order restricted to the table's
non-zero categories (cheap reversible memory work first, script
lifecycles last). The committed plan:

| Table | Architecture | Process candidates | Expected actions | Priority order |
| --- | --- | --- | --- | --- |
| case-01.ct | unknown | `ct2synth01.exe` | 103 | value_freeze, persistent_script |
| case-02.ct | x64 | `ct2synth02.exe` | 150 | value_freeze, string_write, one_shot, persistent_script |
| case-03.ct | x64 | `ct2synth03.exe` | 32 | value_freeze, one_shot, persistent_script |
| case-04.ct | x64 | `ct2synth04.exe` | 25 | value_freeze, persistent_script |
| case-05.ct | unknown | `ct2synth05.exe` | 9 | persistent_script |
| case-06.ct | x64 | `ct2synth06.exe` | 312 | value_freeze, persistent_script, custom_value |
| case-07.ct | x64 | `ct2synth07.exe` | 5152 | value_freeze, string_write, one_shot, persistent_script |
| case-08.ct | x64 | `ct2synth08.exe` | 16 | value_freeze, one_shot, persistent_script |
| case-09.ct | x64 | `ct2synth09.exe` | 6 | persistent_script |
| case-10.ct | x64 | `ct2synth10.exe` | 2 | one_shot, persistent_script |
| case-11.ct | x64 | `ct2synth11.exe` | 114 | value_freeze, persistent_script |
| case-12.ct | x64 | `ct2synth12.exe` | 45 | value_freeze, persistent_script |
| case-13.ct | x64 | `ct2synth13.exe` | 1 | persistent_script |

The case numbers map to the synthetic clean-room corpus
(`TableReferences/README.md` carries the documentation-level origin
provenance); the tables themselves are independently authored and contain
no game content.

Historical totals for the 13-table snapshot: 5,967 expected actions —
value_freeze 3,098, one_shot 1,722, string_write 731,
persistent_script 413, custom_value 3. Current category totals from the
30-table manifest are: value_freeze 3,205, one_shot 1,730,
string_write 732, persistent_script 472, custom_value 4
(6,143 executable actions). Two navigation rows are listed for corpus completeness but are not
counted as AP-11 actions or reportable observations.

The manifest carries a consistency section with eight gates; any failure
is exit 2 and the artifact must not be consumed as evidence:
`pinned_table_count`, `expected_actions` (sum vs the pinned manifest
denominator), `category_counts`, `confirmed_game_effect_zero`,
`per_table_counts` (per table: action-category sum == expected_actions,
record count == expected_actions + navigation exclusions, and the action
categories are within the five), `ct_sha_integrity` (computed CT SHA-256 vs
pinned; a tampered CT fails here and the mismatch is written into the
artifact), `inventory_covers_campaign_shas`, and
`feature_coverage_agrees` (feature-coverage `all_ok`, its
`expected_actions` check agrees with the pinned campaign denominator, its
pinned SHA list equals the campaign's).

Exit codes: 0 ok, 1 input error (missing/invalid inputs, failed report
validation, progress state from a different campaign), 2 consistency
failure, 3 write refusal (never into a directory containing an input
artifact, nor into the read-only corpus root).

## User-machine prerequisites (later, real campaign)

- A Windows machine with the target game installed and the Native 0.9
  trainer EXE(s) built from the pinned CTs (build path per
  `native-runtime.md`); the campaign tool itself is not needed on the
  user machine — only the trainer EXEs and this runbook.
- No Cheat Engine and no Python knowledge required: the procedure below
  is manual (launch game, launch trainer, toggle, observe, record).
- Per table the expected process name is the manifest's
  `process_candidates` entry. If the running process differs (renamed
  EXE, mod, launcher wrapper), record the actual `process_name` in the
  report; the tool validates structure, not process identity.
- Record the game build once per table as `game_build_id` (Steam build
  id or installed version string). It is mandatory for every
  `confirmed=true` observation.
- Work one table at a time, in the table's `priority_order`, and within
  a category from the lowest record ids upward.

## Procedure per action category

Every action goes through the same five-step loop; the category
specifics are what to look for in the readback step.

1. **Attach** — start the game to a stable state (menu or safe level),
   start the trainer EXE, attach to the manifest process candidate.
   Verify the trainer reports a live attach (no stale PID).
2. **Toggle ON** — enable the record (switch ON, or execute the
   one-shot). If the action is a group/parent action, enable it as the
   trainer UI exposes it; record the exact control used.
3. **Readback** — read the value back or observe the in-game effect,
   then trigger the game condition that would normally change it
   (damage tick, item pickup, level change, dialogue). Confirm the
   effect is present and stable across the trigger.
4. **Toggle OFF** — disable the record; verify the original behavior
   returns (value moves again, script effect stops, string reverts).
   For scripts: verify the undo path leaves the original bytes/code.
5. **Re-Attach** — detach, close the trainer, re-attach (or restart the
   trainer) and verify the saved switch state is restored per the
   trainer's restoration policy (only previously confirmed ON states
   are restored; failed attempts must not re-activate).

Category specifics:

- **value_freeze** — readback shows the frozen value holds over several
  natural change cycles; after OFF the value changes again normally.
- **string_write** — the written string appears in the in-game location
  (UI text, item name, etc.); after OFF the original string returns.
- **one_shot** — the one-time effect executes exactly once; re-execution
  is either blocked or idempotent; no lingering state after OFF.
- **persistent_script** — the script effect persists across in-game
  state changes while ON; OFF undoes it cleanly (original bytes/code
  restored, no leaked hooks); scripts with dependencies are enabled
  before the dependent records.
- **custom_value** — the typed custom value (re2.CT) reads and writes
  through the typed value path; readback matches the written value.

For every attempted action record one observation: `record_id`,
`action` (the category), `expected` (what should happen), `observed`
(what actually happened), `confirmed` (true only with verifiable
effect), and `evidence_note` (free text: what was triggered, what the
readback showed, build context).

## Safety rules

- **Fail-Closed.** Any unclear state — error dialog, no observable
  effect, crash, value not restored after OFF, async/script lifecycle
  doubt — is recorded as `confirmed=false` with the observed result.
  Never record `confirmed=true` without a concrete readback and a
  non-empty `game_build_id`. Stop further writes to that record and
  continue with the next record unless the game itself is unstable.
- **Partial-Copy handling.** If a toggle only partially takes effect
  (one of several sub-values changes, a string writes but the UI does
  not refresh), record the partial state exactly as observed, as
  unconfirmed. Do not retry blindly; at most one deliberate retry,
  recorded as its own observation.
- **Cleanup.** After each table session: all switches OFF, detach,
  close the game; never leave freezes or scripts active across a save;
  use a throwaway character/save for effect testing where possible and
  note the changed game state in the evidence note. If the game
  crashes: restart it, re-attach, and re-verify only the last
  unconfirmed action before continuing.
- No process or memory interaction outside the trainer EXE itself; the
  repository machine never attaches to any game.

## Report format v1 (`ap11-report/v1`)

```json
{
 "schema": "ap11-report/v1",
 "table": "case-01.ct",
 "process_name": "ct2synth01.exe",
 "process_pid": 18432,
 "game_build_id": "Steam build 3672045",
 "observations": [
  {
   "record_id": 122,
   "action": "value_freeze",
   "expected": "Health frozen at 100",
   "observed": "Health stayed 100 through three damage ticks",
   "confirmed": true,
   "evidence_note": "readback via trainer value field; damage tick triggered by falling"
  },
  {
   "record_id": 121,
   "action": "persistent_script",
   "expected": "script enabled and held",
   "observed": "script enabled, but disabled itself after menu change",
   "confirmed": false,
   "evidence_note": "lifecycle problem, needs script review; no retry yet"
  }
 ]
}
```

Validation rules (all enforced by `ap11_campaign.py report`):

- `schema` must be `ap11-report/v1`.
- `table` must match a campaign table by `name` or `ct_path`.
- `process_name` non-empty string; `process_pid` positive integer
  (booleans rejected).
- `game_build_id` non-empty string or `null`.
- `observations` is a list; each observation references a manifest
  record of the matched table (`record_id` integer present in the
  table's `records` map), `action` is one of the five categories and
  equals the record's static category, `expected`/`observed` are
  non-empty strings, `confirmed` is a boolean, `evidence_note` is a
  string or `null`.
- `confirmed=true` additionally requires a non-empty `evidence_note`
  and a non-empty `game_build_id`.
- Duplicates on `(record_id, action)` are idempotent: a confirmed
  observation wins over an unconfirmed duplicate, otherwise the first
  one wins; `duplicates_removed` is reported in the summary.
- Any validation error exits 1 and writes nothing.

## Feedback loop (report ingestion on the repository machine)

```
python tools/corpus_denominator/ap11_campaign.py report ^
    --report <report.json> --output <dir> [--campaign <manifest>] [--run-id <id>]
```

Default campaign is the committed `gap_inventory/ap11-campaign.json`.
The tool writes into `--output`:

- `ap11-progress.json` (`ap11-progress/v1`) — cumulative state keyed by
  table name, bound to the campaign manifest's SHA-256. For each table
  the latest report file wins (`report_sha256` stored, not the path,
  so state is machine-independent); re-ingesting the same report file
  is a byte-identical no-op; a different report file for the same
  table replaces the previous observations (`replaced_previous` in the
  summary). A progress state from a different campaign manifest is
  rejected (exit 1).
- `ap11-summary.json` (`ap11-summary/v1`) — every campaign table with
  `confirmed_by_category` and `confirmed_total` against
  `expected_actions`, the ingestion statistics, and `overall`
  progress: `confirmed_actions` vs the current 6143-action denominator,
  `confirmed_percent`, `remaining_actions`, `goal_percent` 90.0 and
  `goal_reached`.

Exit codes as in the manifest path. Once a real user-machine campaign
report is ingested, `confirmed_game_effect_actions` moves off zero for
the first time; until then the denominator document stays
`confirmed_game_effect_actions: 0`.

## Historical verification and current open limits

- Historical focused suite (2026-10-10 baseline): 28 tests OK, including
  byte-identical double runs,
  byte-identical committed baseline regeneration, CT tamper/missing
  integrity, write refusal, report validation/dedup/replacement/state-
  binding (see the focused-suite log of the latest green build run).
- Current 0.16 build suite: 3,398 OK / 25 expected skips; see
  [`plans/TRACKING.md`](../plans/TRACKING.md) for pinned build evidence.
- This lane proves nothing about actual game behavior: no game, process
  or trainer EXE was started here. The AP-11 campaign remains at
  0/6143 confirmed actions. The manifest is a plan, not evidence.
