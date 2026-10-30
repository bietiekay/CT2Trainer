# Subagent Lane Rules (Parallel Implementation + Merge Coordinator)

Status: 2026-10-30. The active objective is 100% trainer/cheat handling for
the 151 local reference-table paths through the independent clean-room
implementation; see
[`plans/reference-table-100-roadmap.md`](../plans/reference-table-100-roadmap.md).
The old AP/WP plans remain design records, not the current goal queue. This
document configures the standing parallel-implementation mechanism used by
the root agent (merge coordinator) and the subagent lanes it spawns. A new
lane starts only after root assigns a bounded package with a current
baseline, an independently authored synthetic case, file ownership and
acceptance checks. Session-specific user launch instructions take precedence
over the standing load check in `AGENTS.md`.

## 1. Roles and work modes

Every session is in exactly one of two work modes.

### 1.1 Root / merge-coordinator mode (owns `main`)

The root agent is the single integration point. It owns:

- `main` and the milestone working branch (`native-<version>-<topic>`):
  branch creation, merging lane branches (normal merge, never force), and
  pushing to both remotes (origin ssh + github) with `git ls-remote`
  verification on each.
- All root docs: `STATUS.md`, `plans/TRACKING.md`,
  `plans/reference-table-100-roadmap.md`,
  `documentation/native-progress.md`, `AGENTS.md` — updated in the same
  change as the content they describe (roadmap status + measured catalog
  delta, release record, superseded-build chain).
- Catalog remeasurements (run id `blocked-catalog-<topic>`), the
  feature-matrix state, and the zero-unexplained-regression rule (§11).
- Version bumps (root `VERSION` + `src/ct2trainer/__init__.py`
  `__version__` + `CHANGELOG.md` in the same change as a build cut) and all
  builds exclusively through `scripts/Build-Native.ps1`, with build
  evidence in `build/runs/<id>/` (`ce_inputs: []` verified, suite result
  and ZIP hashes recorded).
- Field-test follow-ups (Windows clean-machine protocol, real Steam Deck
  under Proton with touch operation), which stay root/user work and are
  recorded in the docs before any status raise.

While lanes run in parallel, root keeps advancing root-owned work
(finishing in-progress packages, doc updates, load checks, lane review) —
it never idles waiting for lanes.

### 1.2 Lane mode (subagent sessions)

Each lane owns exactly ONE bounded work package (feature wiring + tests, or
an explicitly assigned analysis deliverable) in its own git worktree and
branch:

- The work package assignment carries: the package goal with the current
  baseline, the leading table/corpus shape to inspect, the independently
  authored synthetic case, the file ownership map (§2) and the acceptance
  checks.
- A lane does not merge, does not push, does not work on `main` or any
  other branch than its own lane branch, and never touches another
  lane's worktree or branch.
- Root docs are read-only for lanes: they report measured numbers, deltas
  and test counts instead of editing docs (§10 report, §11 root
  procedure).

### 1.3 Launch rule (load gate)

Before every new lane launch, root checks the model-server load with
`tools/agent_load.py` (sglang metrics endpoint; exit 0 = at least one lane
may launch, exit 1 = defer). Launch new agents only when the request queue
is empty, the free KV span is substantial and the abort counter is flat.
Parallelize lanes up to the actual capacity of the server so the available
resources are used optimally; never blindly launch into a saturated server.
A launch that fails or is saturated is reported to the user, not retried
blindly.

## 2. Parallelization and file ownership

Parallel lanes are safe only when their file footprints are disjoint or
conflict-free by review. Root assigns the ownership map per campaign:

- Which files each lane owns, and which areas stay root-owned.
  Example for the 0.20 RT-5 B/E cycle: lane B (code patch) owns
  `src/ct2trainer/native/compiler.py`, `src/ct2trainer/native/engine.py`,
  `src/ct2trainer/native/ui_rows.py`, the CheatCodes parsing area of
  `src/ct2trainer/table.py` and its own new test files; root (item E) owns
  `src/ct2trainer/native/lua_host.py`, the external-action warning area of
  `src/ct2trainer/table.py` and the item-E test files.
- A lane may touch a shared file only inside its owned area, with the
  minimal hunks required; every shared-file touch is listed in the report
  ("Integration notes") so root can review for conflicts.
- If two lanes need the same file area, root assigns it to one lane and the
  other waits or works around it. Lanes never resolve each other's
  conflicts.
- Test files: each lane gets its own dedicated test file(s) for its
  feature. Shared pin files (existing tests that pin a behavior the lane
  replaces) are updated by the implementing lane, and every such update is
  listed in the report.

## 3. Read first (in your worktree)

1. `AGENTS.md` — project boundaries (Native edition: no CE implementation
   inputs or binaries; public API/format contracts may be derived).
2. `plans/TRACKING.md` and `plans/reference-table-100-roadmap.md` — the
   active package and completion gates. Read historical AP/WP plans only
   for relevant design detail.
3. `documentation/native-progress.md` — current state and open list.
4. This file — roles, ownership, workspace, test and reporting contracts.

## 4. Absolute prohibitions (NEVER)

- No copying or deriving CE implementation code. The Cheat Engine 7.5
  source tree at `C:\Users\xboxl\code\cheat-engine-7.5` is a
  **behavior reference only** (2026-10-13 user decision): you may READ it
  to understand how CE handles a behavior, but every implementation stays
  clean-room — no copied, derived or ported code, no CE binaries. All
  other CE implementation sources remain off-limits.
- No writes to `TableReferences/` (strictly read-only corpus input).
  The synthetic corpus is fully committed; a file missing from your
  worktree means a stale checkout — sync from the main checkout first,
  and stay read-only. The local original reference tables under
  `C:\Users\xboxl\code\reference-table-input-do-not-add-to-git` are
  read-only inputs that never enter git or releases.
- No modifications of root-owned files:
  `STATUS.md`, `tools/corpus_denominator/*`, `gap_inventory/*`,
  `tests/test_native_feature_matrix.py`,
  `tests/test_native_ap11_campaign.py`,
  `tests/test_native_corpus_traceability.py`,
  `plans/*`, `documentation/*`.
  (Read them freely; report the proposed matrix entry instead of editing.)
- No work on `main` or the milestone working branch; no merges, no
  pushes, no force-pushes from the lane; never touch the worktrees or
  branches of other lanes.
- No deletion or blind cleanup of `build/`, `.tools/`, `dependencies/`,
  `gap_inventory/`, fixtures or evidence.
- No new third-party dependencies. Stdlib + pinned local tooling only.
- Do not rewrite or weaken existing tests. Extending an existing test file
  is allowed only when the feature has no natural home in a new dedicated
  file; prefer a new dedicated file.
- Do not fake coverage. If the feature cannot be wired without real game
  files, real Windows-only APIs or live targets, stop and report
  BLOCKED with evidence — the root agent decides.

## 5. Workspace and tool paths

You work in your assigned worktree (given in your task). `.tools/` is
gitignored and therefore ABSENT in every worktree — use the shared
tooling of the main checkout. Locate it with `git worktree list` (the
checkout root of the primary worktree) and replace `<main>` in the
commands below with that path. All other paths are relative to your own
worktree root.

- Python interpreter:
  `<main>\.tools\native-build-env\Scripts\python.exe` (development venv,
  Python 3.12 with Lupa 2.8 / iced-x86 1.21.0; if it is missing in the
  main checkout, create it there first per `documentation/build.md` §1).
- NASM (full suite only):
  `<main>\.tools\native-tools\nasm.exe` (restored into the main checkout
  with `python tools/native_build.py restore-nasm --output .tools/native-tools`).
- If the shared venv is unavailable, the newest green build run folder
  under `build/runs/` carries its own `venv\Scripts\python.exe` and
  `native-tools\nasm.exe` — prefer that over re-creating tooling.
- `PYTHONPATH` must point at YOUR worktree's `src` and `tests`.

Set `workdir` to your worktree for every shell command.

## 6. Test commands (PowerShell)

Focused (fast iteration):

```powershell
$env:PYTHONPATH = (Resolve-Path src).Path + ";" + (Resolve-Path tests).Path
$env:PYTHONIOENCODING = "utf-8"
& "<main>\.tools\native-build-env\Scripts\python.exe" -m unittest tests.test_native_<module> -v
```

Full suite (mandatory before reporting):

```powershell
$env:PYTHONPATH = (Resolve-Path src).Path + ";" + (Resolve-Path tests).Path
$env:CT2TRAINER_NASM = "<main>\.tools\native-tools\nasm.exe"
$env:PYTHONIOENCODING = "utf-8"
& "<main>\.tools\native-build-env\Scripts\python.exe" -m unittest discover -s tests -p 'test_native_*.py' 2>&1 | Out-File -FilePath $env:TEMP\lane-full.log -Encoding utf8
Get-Content $env:TEMP\lane-full.log | Select-String -CaseSensitive 'Ran \d+ tests|^OK|FAILED' | Select-Object -Last 3
```

Baseline at the lane base commit: **3,850 OK / 26 expected skips**
(verified on `main` @ `7d42887`, the 0.19 field-fix cycle; re-verify
against your exact base commit before relying on it). Your final full
suite must be that baseline plus your new tests, zero failures.

PowerShell pitfalls (learned the hard way):

- No `head`; use `Select-Object -First/-Last`.
- No `Get-Date -AsUtc`; compute UTC timestamps with Python
  (`datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')`).
- Console is cp1252 — always set `$env:PYTHONIOENCODING="utf-8"` before
  Python output with umlauts or `→`.
- unittest writes its summary to stderr → PowerShell reports
  `NativeCommandError` and exit code 1 even on success. Always capture to
  a log file and filter with `-CaseSensitive` (otherwise `all_ok: True`
  lines from corpus tools match `OK`).
- `git commit -m '...'` in single quotes; keep the subject detailed, in
  English, matching the style of `git log --oneline -10`.
- The edit tool can mis-indent markdown bullets; after doc-adjacent text
  edits, verify with a byte dump
  (`python -c "print(repr(open(path,'rb').read()[i-40:i+200]))"`) if an
  edit reports no match.

## 7. Coding conventions (house style)

- Fail-closed: every refused input raises a NAMED exception (existing
  refusal classes where present; new named `ValueError` subclasses for a
  new module). Never silent fallbacks, never `try/except: pass`.
- Bounded inputs: validate lengths, counts, ranges at the boundary of
  every public entry point.
- Deterministic outputs: sorted casefolded keys (`key=str.casefold`) for
  all list/manifest fields; byte-stable serialization where the module
  serializes plans.
- Match surrounding style: no gratuitous refactors, no new abstractions
  beyond the wiring contract, keep diffs tight.
- Plan metadata must be byte-verifiable: anything you add to a program or
  entry dict must be derivable from the source by the existing
  regeneration/consistency checks (`validate_program`, `validate_plan`,
  profile consistency).
- Reuse tested stage-1/stage-2 models; do not re-derive their logic.
- No logging side effects in models; engine state changes only through
  the existing transaction paths (do not bypass `_install_program`,
  hook managers or the freeze/value runtime).

## 8. Test conventions

- Dedicated positive test file: `tests/test_native_<snake_case_feature>.py`
  (e.g. `test_native_recursive_parent_value.py`). It must test the feature
  POSITIVELY end-to-end (compile → plan → engine → byte-exact effect),
  not only refusals.
- Reuse existing fixture scaffolding:
  - `FakeMemory` (`tests/test_native_engine.py`), `Memory`
    (`tests/test_native_lua_activation.py`), `CodeMemory`/`Coordinator`
    (`tests/test_native_engine_code.py`) — engine-level test shape: see
    `tests/test_native_dropdown_link.py` (setUp/tearDown,
    `memory_factory=lambda name: self.memory`, `hook_coordinator=...`,
    `engine.poll()`, byte assertions on `memory.data`, `memory.writes`
    for no-write assertions).
  - Synthetic binary fixtures: `tests/native_il2cpp_static_fixtures.py`
    and the per-module fixture builders.
  - CT bodies as Python strings written to a temp directory, then
    `compile_table(path, "FixtureTarget.exe")`.
- Cover at minimum: the happy path with byte-exact assertions, the
  disable/restore roundtrip, plan metadata presence and consistency,
  forged/tampered metadata rejection by BOTH plan validators (compiler
  and engine `validate_plan`), and every fail-closed refusal your wiring
  introduces (assert no `memory.writes` after each refusal).
- Corpus fidelity: your fixture shapes must mirror the pinned corpus
  records from `gap_inventory/gap-report.json` (gap class → records →
  the exact CT under `TableReferences/`, read-only).
- No test may parse `plans/` or `documentation/`.

### 8a. Pinned rejection tests for the behavior you are wiring

If an existing test pins the exact fail-closed rejection that your wiring
replaces (the active grammar refusing the very feature you implement, e.g. a
`ProgramError` for `{$if}` blocks before conditional wiring, or the
fail-closed `luaCall` refusal), that test pins a pre-feature state, not a
permanent contract: update it to the new accepted behavior, and keep every
still-valid refusal sub-case (malformed input, undefined define, unbalanced
blocks, ...) covered as refusals in your dedicated file or the same file.
Rejection pins for OTHER features must remain byte-identical.

## 9. Definition of "covered" (matrix convention)

A feature flips partial→covered only when:

- it is integrated into the product path (compiler emits plan metadata,
  the engine executes it at runtime), and
- a dedicated positive test file proves it on own synthetic fixtures.

Real in-game effect, real Windows process APIs, real game/Unity files and
every AP-11 gate remain open by definition and are recorded in the
matrix note by the root agent — never a lane deliverable.

## 10. Definition of done (lane)

1. Focused suite for your modules: green.
2. Full suite: green (baseline + your new tests, zero failures).
3. Exactly ONE commit on your lane branch: implementation + tests only.
   Message: `Native <feature> wiring: <what was added, which modules,
   which behaviors, refusal cases, test counts, full suite result>`.
4. Report filled in (section 11) in your final message.

## 11. Report format (final message, exact sections)

```
LANE REPORT — <feature>
Branch/commit: <branch> @ <sha>
Files added: <list>
Files modified: <list>
Tests: focused <n> OK; full suite Ran <n> / OK / skipped=<n>
Design decisions:
- <3–6 bullets: plan fields added, engine behavior, where resolution
  happens, which existing model was reused, deliberate scope limits>
Wiring contract:
- plan metadata: <field names, shape, consistency guarantee>
- runtime: <when/where the engine executes it, injected dependencies>
- refusals: <each named refusal + trigger>
Open gates (for the matrix note): <what stays open, e.g. AP-11>
Integration notes: <shared files touched (engine.py/compiler.py/...),
  new public surface (constructor params, protocol methods), known
  conflict risk with other lanes>
```

If BLOCKED: replace the report with `LANE BLOCKED — <feature>` plus the
concrete blocker and the evidence you gathered; do not commit partial
work.

## 12. Root merge-coordinator procedure (root agent only, not a lane task)

After a lane reports DONE:

1. Review the lane branch diff against its report (files, design
   decisions, shared-file touches).
2. Merge the lane branch into the milestone working branch (normal
   merge, never force). Resolve any conflicts at root; a conflict
   indicates an ownership-map error — tighten the map for the next
   campaign.
3. Run the canonical full suite (CT2TRAINER_NASM) on the merged branch.
4. Remeasure the original-table catalog with the lane's expected delta as
   the acceptance check: `total_entries` / `supported` changes must
   match the lane report; **zero unexplained supported regressions** —
   every newly blocked row needs a named, catalog-visible reason, and
   every reason-only change is documented. Record the run under
   `blocked-catalog-<topic>` with the baseline chain (previous run ids)
   in the docs.
5. Update root docs in the same change: roadmap status + measured delta,
   `plans/TRACKING.md`, `documentation/native-progress.md`, `STATUS.md`,
   `AGENTS.md`.
6. If the change triggers a release: bump `VERSION` + `__version__` +
   `CHANGELOG.md` in the same change as the build cut; build only via
   `scripts/Build-Native.ps1`; verify `ce_inputs: []` and the in-build
   suite; record the build (run id, ZIP hashes, suite result) in
   `AGENTS.md` / `STATUS.md` with the superseded-build chain.
7. Push the milestone branch and `main` to both remotes (origin ssh +
   github) and verify each with `git ls-remote`.

## 13. Work modes for validation and release (RT-6 / RT-7)

- RT-6 (full original-table validation) splits into two modes:
  - **Plan inspection (parallelizable):** root splits the 151 paths into
    chunks (per game family or alphabetically) and assigns one chunk per
    lane; each lane produces the per-path plan-inspection result plus an
    honest skip record for every target it cannot access (pinned game
    build not available, no live runtime observation possible).
  - **Runtime observation (root/user field work):** targeted observations
    against pinned game builds, the Windows clean-machine protocol and
    the Deck/Proton/touch protocol. `runtime_unverified` stays set until
    both pass; observations are recorded in the docs before any status
    raise.
- RT-7 (release gate) is single-threaded at root: rebuild only through
  `scripts/Build-Native.ps1`; full suite and source/frozen parity;
  `ce_inputs: []`; archive hashes and provenance; update tracker, ledger
  and verification before declaring 100%.
