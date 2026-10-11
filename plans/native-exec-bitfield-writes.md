# CT2Trainer: Executable-Literal Bitfield Writes (WP-15, L2-37)

**Status:** Plan (2026-10-11) — Baseline: `main` @ `7927cb4` (0.10, suite
2671 OK / 25 expected skips)

Closes **L2-37** from the CE7.5 comparison: the single open P0 write-path
limit. Masked (bitfield) writes and freezes into source-proven executable
literal spans are refused fail-closed today, while full-span numeric writes
and freezes on the same spans are supported.

## 1. Current state (verified 2026-10-11)

- `Binary` CT records compile to a `value_profile` of kind `bitfield`
  (`compiler.py:581-592`, `value_types.py:107-117`); mask / merge / parse
  helpers live in `value_types.py` (`_mask` 150-155,
  `merge_profile_value` 169-185, `profile_value_matches` 188-197). The
  profile is re-derived and tamper-refused at compile
  (`compiler.py:794-806`) and at trainer load (`engine.py:270-282`).
- Full-span numeric writes/freezes on executable literal spans already work
  via `_write_owned_literal_values` (`engine.py:1944-1967`): every span must
  be executable, each must be fully covered by one live source-proven
  literal permit from `_owned_provider_data()`; staging goes through a
  transient `HookManager` (`literal_data=True, data_semantics=True,
  requires_coordinator=True`, `owned_executable_data_ranges=permits`),
  published under the safe-point hold, terminated with `commit_data_only()`,
  manager retired; controller quarantined on uncertainty.
- Masked writes are refused:
  - R1 `engine.py:3306-3307` (`_write_bitfields`): any executable span →
    `Masked bit-field writes to executable provider data require a separate
    profile`.
  - R2 `engine.py:3562-3564` (`set_freeze`): executable bitfield → `Masked
    bit-field freezes on executable provider data require a separate
    profile`.
- Data-page bitfields use the data-only `hold_data` coordinator path, which
  is structurally incapable of covering executable pages
  (`debug_coordinator.py:260-277`). R1/R2 are early, visible forms of that
  boundary, not oversights — the new path must restore the same guarantees
  through the hook/coordinator path.

## 2. Scope decisions (root, 2026-10-11)

1. **Bitfields only.** Only `value_profile.kind == 'bitfield'` moves. String
   and byte-array writes on executable spans keep their existing refusal
   (the `_check_data_windows` boundary is unchanged).
2. **No AA dialect change.** The parsed AA grammar has no masked-write form
   (whole-size `db/dw/dd/dq` only, `aa_program.py:884`).
3. **Freeze ticks pay the safe-point hold per tick** — same cost profile as
   today's full-span numeric freezes on executable literals.
4. **Recursive closures keep refusing** bitfield records
   (`_set_recursive_value`, R3): the static closure plan carries no RMW
   snapshot.
5. **Test supersession (root-approved):**
   `test_exec_bitfield_refused_before_mutation`
   (no provider → refusal) stays unchanged and must keep passing.
   `test_exec_bitfield_freeze_refused_before_recording_even_with_literal_permit`
   pins a scenario that becomes supported; it is superseded in place: the
   test keeps its shape (refused before recording, no frozen entry, no
   writes, no holds) but the setup grants a permit that does **not** fully
   cover the span (partial coverage → refusal). The supported case moves to
   the new dedicated test file.

## 3. Design

Route fully-permitted executable bitfields through the existing
literal-data hook path, mirroring `_write_owned_literal_values`:

- `_write_bitfields`: classify each item's span. If **all** spans are
  executable:
  1. require the hook coordinator;
  2. fetch live permits via `_owned_provider_data()`; every merged span must
     be fully covered by one live permit (same coverage rule as
     `engine.py:1949-1950`);
  3. fresh snapshot read under the safe-point hold, through a transient
     `HookManager` staged with the **merged** bytes (RMW: fresh snapshot →
     `merge_profile_value` per field → stage block with `original` from the
     held read, `literal_data=True, data_semantics=True,
     requires_coordinator=True`, blocks bound to the permit's allocation
     `literal_data_ranges`);
  4. `publish()`, `commit_data_only()`, retire the manager;
  5. on uncertainty: quarantine the controller, retain evidence, no
     follow-up writes.
  All spans non-executable: today's `hold_data` path, unchanged. Mixed
  executable + non-executable batches: keep a named refusal (extend the
  R7 "Mixed ordinary/executable" semantics).
- `set_freeze` (R2): replace the blind refusal with the same permit
  coverage pre-check; refuse **before** recording when coverage is missing
  (a failed enable stays visibly inactive — no saved wish).
- The `poll` tick needs no direct change (it routes through
  `_write_bitfields`).
- **No** plan JSON fields, no validator changes, no bundle changes, no
  `gap_inventory/` changes (zero `BitStart` records in the pinned corpus).

## 4. Lane ownership

- Branch `wp15-exec-bitfield` cut from `native-l2-37`; worktree
  `C:\Users\xboxl\AppData\Local\Temp\opencode\wp15-execbitfield`.
- Touchable: `src/ct2trainer/native/engine.py`,
  `tests/test_native_exec_bitfield_runtime.py` (new),
  `tests/test_native_value_runtime.py` (supersede one test per §2.5 only).
- Root-owned (do NOT modify; report needed updates in the final report):
  `plans/*`, `documentation/*`, `gap_inventory/*`, `CHANGELOG.md`,
  `AGENTS.md`, `TableReferences/*`.
- No new third-party dependencies; no pushes; no commit to `main`.

## 5. Acceptance

- New `tests/test_native_exec_bitfield_runtime.py` (fixtures: synthetic
  provider hook with a literal hole + real `Binary` record pointing into
  it), covering:
  - set_value happy path: merged bytes on disk, unowned neighbour bits
    preserved, provider still enabled, durable data receipt;
  - freeze: enrollment OK; tick re-merges preserving fresh unowned bits;
    tick after provider disable / permit revocation → refusal, controller
    quarantined, no writes;
  - kept refusals: no live permit; partial permit coverage; span crossing a
    permit boundary; mixed executable/ordinary batch;
  - template case: engine-level full-span numeric write on a live provider
    span (today only hook-layer tests cover that path).
- Superseded test replaced in place per §2.5;
  `test_exec_bitfield_refused_before_mutation` untouched and green.
- Suite green at the canonical path; in the worktree only the three known
  provenance byte-identity tests may fail (see §6).
- `git diff --stat` against the branch base shows **no** `gap_inventory/*`
  changes.

## 6. Known worktree caveat

In any non-canonical worktree, exactly three tests fail because the
committed artifacts embed the canonical absolute paths:
`test_committed_manifest_is_byte_reproducible`
(`tests/test_native_repro_chain.py`),
`test_02_feature_matrix_reproduces_feature_coverage`
(`tests/test_native_feature_matrix.py`),
`test_03_ap11_reproduces_campaign_manifest`
(`tests/test_native_ap11_campaign.py`). Verified 2026-10-11 in a scratch
worktree (43/46 OK, exactly those three fail). Do **not** try to "fix"
them in the lane; root re-runs the full suite at the canonical path at
integration.

## 7. Log

| Date | Change / next checkpoint | Evidence / open work |
| --- | --- | --- |
| 11.10.2026 | WP-15 plan; investigation report (refusal map R1–R11, data model, behaviour matrix, test inventory) | baseline `main` @ `7927cb4` (0.10) |
| 11.10.2026 | **WP-15 complete**: lane `wp15-exec-bitfield` (tests-first `78b2385`, implementation `8dcd92d`) merged into `main` @ `d3316aa`; root docs updated at integration | worktree suite 2680 OK / 25 skips / 3 expected provenance failures; canonical-path suite **2688 OK / 25 skips / 0 failures** (2026-10-11); exactly 3 files changed: `engine.py`, `tests/test_native_exec_bitfield_runtime.py` (new, 9 tests), `tests/test_native_value_runtime.py` (one in-place supersession per §2.5) |
