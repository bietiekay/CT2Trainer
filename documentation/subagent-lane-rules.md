# Subagent Lane Rules

Operational contract for implementation lanes spawned by the root agent on
the current milestone. Each lane owns exactly ONE work package
(feature wiring + tests) in its own git worktree and branch. The root agent
performs all integration, matrix flips, artifact regeneration, doc updates
and pushes.

## 1. Read first (in your worktree)

1. `AGENTS.md` — project boundaries (Native edition: no CE implementation
   inputs or binaries; public API/format contracts may be derived).
2. `plans/native-implementation-continuation.md` — the relevant AP section
   for your feature, §5 (work package status) and §7 (commit/push
   protocol).
3. `documentation/native-progress.md` — current state and open list.
4. This file — workspace, test and reporting contracts.

## 2. Absolute prohibitions (NEVER)

- No copying or deriving CE implementation code. The Cheat Engine 7.5
  source tree at `C:\Users\xboxl\code\cheat-engine-7.5` is a
  **behavior reference only** (2026-10-13 user decision): you may READ it
  to understand how CE handles a behavior, but every implementation stays
  clean-room — no copied, derived or ported code, no CE binaries. All
  other CE implementation sources remain off-limits.
- No writes to `TableReferences/` (strictly read-only corpus input).
  The synthetic corpus is fully committed; a file missing from your
  worktree means a stale checkout — sync from the main checkout first,
  and stay read-only.
- No modifications of root-owned files:
  `tools/corpus_denominator/*`, `gap_inventory/*`,
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

## 3. Workspace and tool paths

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

## 4. Test commands (PowerShell)

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

Baseline at the lane base commit: **2698 OK / 25 skips** (verified on
`main` after the WP-17 integration; re-verify against your exact base
commit before relying on it). Your final full suite must be that
baseline plus your new tests, zero failures.

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

## 5. Coding conventions (house style)

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

## 6. Test conventions

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

### 6a. Pinned rejection tests for the behavior you are wiring

If an existing test pins the exact fail-closed rejection that your wiring
replaces (the active grammar refusing the very feature you implement, e.g. a
`ProgramError` for `{$if}` blocks before conditional wiring, or the
fail-closed `luaCall` refusal), that test pins a pre-feature state, not a
permanent contract: update it to the new accepted behavior, and keep every
still-valid refusal sub-case (malformed input, undefined define, unbalanced
blocks, ...) covered as refusals in your dedicated file or the same file.
Rejection pins for OTHER features must remain byte-identical.

## 7. Definition of "covered" (matrix convention)

A feature flips partial→covered only when:

- it is integrated into the product path (compiler emits plan metadata,
  the engine executes it at runtime), and
- a dedicated positive test file proves it on own synthetic fixtures.

Real in-game effect, real Windows process APIs, real game/Unity files and
every AP-11 gate remain open by definition and are recorded in the
matrix note by the root agent — never a lane deliverable.

## 8. Definition of done (lane)

1. Focused suite for your modules: green.
2. Full suite: green (baseline + your new tests, zero failures).
3. Exactly ONE commit on your lane branch: implementation + tests only.
   Message: `Native <feature> wiring: <what was added, which modules,
   which behaviors, refusal cases, test counts, full suite result>`.
4. Report filled in (section 9) in your final message.

## 9. Report format (final message, exact sections)

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

## 10. Root integration procedure (root agent only, not a lane task)

After a lane commit is merged into the milestone working branch:

1. Matrix flip in `tools/corpus_denominator/feature_matrix.py`
   (partial → covered; update evidence, modules, note with the new open
   gates).
2. Regenerate both `gap_inventory/` artifacts atomically with ONE fresh
   UTC run id (`lane-feature-matrix-<TS>Z` and
   `lane-ap11-campaign-refresh-<TS>Z`), copy both into `gap_inventory/`,
   update the pins in `tests/test_native_feature_matrix.py`.
3. Commit matrix + artifacts + pins as one commit.
4. Update Plan §8 rows and `documentation/native-progress.md`; commit docs
   as a second commit.
5. Run the full suite green, then push the milestone working branch,
   merge it into `main` (normal merge, never force), and push `main` — so
   both branches track the milestone continuously between cycle-end
   releases (AGENTS.md workflow policy).
