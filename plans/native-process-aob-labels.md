# CT2Trainer: `$process` AOB Module Token + Trailing `@F` Resolution (WP-18)

## 1. Current state (verified 2026-10-11)

Reference table `PRAGMATA.CT` (user-owned, `side/reference/PRAGMATA.CT`,
never committed to the repo): 595 records, 586 supported, 9 blocked.
The 9 blocked records form one causal chain with exactly two root causes
(probe evidence in `side/evidence/probe_wp18.out`, `side/evidence/probe_bisect.py`):

**Root cause 1 — the `$process` AOB module token (records 11 and 25).**
Both are AOBMaker-generated `aobscanmodule(LABEL, $process, <pattern>)`
scripts. The bounded compile path (`compile_script` in
`src/ct2trainer/native/aa.py`, `aobscanmodule` handler ~lines 196–206)
runs `validate_expression('"' + module + '"')` on the module argument, and
the quoted `"$process"` is not a module basename, so the script is refused
with `Unsupported address expression: '"$process"'.` The program path
already tolerates the token: `aa_program.py:327` skips the expression check
when the module is `$process`, and `preflight_program`
(`aa_program.py:947`) already maps `"$process"` →
`program["process_name"]` before calling `memory.scan_module`.
Missing today: the bounded path (aa.py) and the engine runtime dispatch —
the two `op == "scan"` sites in `src/ct2trainer/native/engine.py`
(~lines 1822–1823 and ~2386–2387) pass `op["module"]` straight to
`memory.scan_module`, where `module("$process")` cannot resolve.

**Root cause 2 — a trailing `@F` with no following `@@` (records 11 and 25).**
Both scripts use the cascading-check idiom:
```
  cmp ... / vucomiss ...
  jne short @F      (or: ja short @F)
  mov [i_base_X], rax
  jmp code
@@:
  <next check>
```
The last check in each script ends with `jne short @F` (entry 11, line 62)
/ `ja short @F` (entry 25, line 43) with **no `@@` anywhere after it**; the
next positioned label is the named `code:` label, which is the intended
target (skip the last store, fall through to `code:`).
`prepare_program` requires every `@f` operand to have a forward `@@`
cursor in the same phase (`aa_program.py:781–787`) and resolves `@f`
only against `@@` positions (`~1653–1654`), so both scripts fail with
`Anonymous forward/backward label has no target.` Bisect (probe):
replacing `$process` with a valid module name leaves the identical label
error, so the two root causes are independent; a minimal `@F`/`@@:` pair
parses fine, so the basic idiom is already supported.

**Cascade (records 12–17, 26).** Entry 11 registers
`i_base_Lunafilament_addr`, `i_base_upgrades_addr`, `i_base_coin_addr`,
`i_base_repair_pack_addr`, `i_base_data_13_addr`, `i_base_data_19_addr`;
entry 25 registers `i_base_last_data_addr`. These are the only providers
of those symbols, so the seven value records report
`Required symbol has no unique supported provider: i_base_*_addr.`

**No corpus impact.** The 14 pinned corpus tables contain no `$process`
module token and no trailing-`@F` shape; the committed corpus has 0
blocked records (`gap_inventory/gap-report.json`, run
`wp14-staged-20261011T093320Z`). No matrix flip and no artifact
regeneration are needed for this work package.

**Existing pins that stay valid.**
`tests/test_native_assembler.py::test_unbound_anonymous_labels_rejected_during_prepare`
(bare `jmp @f` / `jmp @b` with no label at all → "no target") remains
correct under the new semantics: with no forward target of any kind the
refusal is unchanged.

## 2. Goal

Unblock the two PRAGMATA root scripts and their seven symbol dependents
(595/595 supported/staged on that reference table) by adding, with
fail-closed discipline:

1. the `$process` module token for `aobscanmodule` in the bounded compile
   path and the engine runtime dispatch;
2. a documented fallback for a forward anonymous reference with no
   explicit `@@` target.

## 3. Design decisions (root, 2026-10-11)

1. **`$process` is a first-class `aobscanmodule` module token** meaning the
   main module of the attached process:
   - bounded path (`aa.py`): skip the quoted-module expression validation
     exactly when the stripped module argument is `$process` (mirror
     `aa_program.py:327`); the emitted op keeps `"module": "$process"`;
   - engine runtime: at every `op == "scan"` dispatch site, map
     `"$process"` → `self.plan["process_name"]` (the exact EXE name pinned
     by the plan validator) before calling `memory.scan_module` — the same
     mapping `preflight_program` already performs (`aa_program.py:947`);
   - program path and preflight: already in place; tests pin the
     behaviour.
   The plan schema, validators and frozen payloads are untouched (the
   token is legal at parse time already, so plans round-trip unchanged).
2. **Trailing `@F` fallback semantics.** A forward anonymous reference
   (`@F`) that has **no explicit `@@` after it in the same phase** resolves
   to the **next positioned named label in that phase** — a label declared
   via `label(...)` or a plain label inside a program-owned allocation
   (the same criterion the generation pass uses for located/local
   labels). If no such forward target exists, the existing fail-closed
   refusal `Anonymous forward/backward label has no target.` is kept.
   `@B` is unchanged (a preceding explicit `@@` is still required).
   Programs where a forward `@@` exists are unaffected, byte-identically
   (the explicit `@@` always wins over the named-label fallback).
   Rationale: the idiom is derivable from public table shapes
   (AOBMaker-style cascading checks) and is strictly additive — it only
   accepts programs that were previously refused.
   Implementation points: the validation loop (`aa_program.py:781–787`)
   and the per-instruction forward selection (`~1653–1654`); the
   named-label positions must come from the same located bookkeeping the
   generation pass uses, and the resolved label name must be the NASM
   spelling from the `names` mapping.
3. **No new refusals, no weakened refusals.** Every previously refused
   shape without a resolvable forward target keeps its exact named error;
   the existing pin tests must stay green unchanged.

## 4. Lane ownership

Files the lane owns (exactly):

- `src/ct2trainer/native/aa.py` — bounded `aobscanmodule` `$process`
  acceptance.
- `src/ct2trainer/native/aa_program.py` — trailing-`@F` check + resolution.
- `src/ct2trainer/native/engine.py` — `$process` mapping at the two
  `op == "scan"` dispatch sites.
- `tests/test_native_process_aob_label.py` — new dedicated test file.

Zero changes to: plan schema/validators, `compiler.py`, `bundle.py`,
`gap_inventory/*`, `TableReferences/`, `plans/*`, `documentation/*`,
existing test files (the existing pins in
`tests/test_native_assembler.py` must remain byte-identical).

The lane may read `side/reference/PRAGMATA.CT` (read-only, user reference
table) to verify fixture-shape fidelity, but must never copy table
content into the repo, tests or commits.

## 5. Tests (minimum, `tests/test_native_process_aob_label.py`)

1. Program path accepts the token: `prepare_program` on
   `aobscanmodule(L, $process, <pattern>)` + `readmem` save + `dealloc`
   disable succeeds; the emitted scan op carries `"module": "$process"`.
   A quoted module name still compiles; a path-like module (e.g.
   `"C:\x\y"`) still raises.
2. Bounded path accepts the token: `compile_script` on a data-only script
   using `aobscanmodule(L, $process, <pattern>)` succeeds with
   `"module": "$process"` in the scan op.
3. Preflight maps the token: `preflight_program` with the token against a
   `Memory` fixture seeded with the scan pattern in the process main
   module resolves the symbol into that range, and `scan_module`/
   `module` are never called with the literal `"$process"` (spy or
   seeded-fixture assertion).
4. Engine dispatch maps the token: engine-level fixture (shape of
   `tests/test_native_engine.py` / `tests/test_native_process_aob.py`)
   where the enabled plan contains a scan op with `module="$process"` —
   `memory.scan_module` receives `plan["process_name"]`.
5. Trailing `@F` positive end-to-end: a synthetic fixture mirroring the
   PRAGMATA shape (chained `cmp`/`jne short @F` / `@@:` blocks, final
   `jne short @F` with no trailing `@@`, named `code:` label,
   `reassemble(<scan label>)`, `registersymbol` of the data labels,
   `[DISABLE]` with `readmem` restore) — `prepare_program` succeeds,
   `link_program` with the real NASM (skip pattern like
   `RealNasmTests`) produces a final branch whose target equals the
   `code:` label position, and `preflight_program` against a seeded
   memory resolves the scan symbol and passes.
6. Fail-closed shapes kept: `jmp @f` with no `@@` and no forward named
   label → `ProgramError` matching "no target" (mirrors the existing pin,
   now also asserted in this file); `@b` with no preceding `@@` → still
   refused.
7. Explicit-`@@` precedence: a `@f` reference that has both a forward
   `@@` and a forward named label resolves to the `@@` (regression guard
   for the unchanged old semantics).

## 6. Acceptance

- Focused file green; full suite green at the lane base (2698 OK / 25
  skips) plus the new tests, zero failures — except the three known
  worktree provenance failures when run off-canonical (see §7).
- `tests/test_native_assembler.py` green and byte-identical.
- Real-table acceptance (root, at integration): recompile the reference
  `PRAGMATA.CT` with the merged compiler — entries 11 and 25 become
  supported, entries 12–17 and 26 become staged on their providers,
  blocked count 9 → 0.
- Integration (root agent): canonical-path full suite,
  `documentation/native-progress.md` note (PRAGMATA reference table fully
  supported, no corpus/matrix change), WP-18 row in
  `plans/native-implementation-continuation.md` §5, worktree/branch
  cleanup, push.

## 7. Known worktree caveat

Off-canonical worktrees fail exactly three provenance byte-identity tests
(`test_committed_manifest_is_byte_reproducible`,
`test_02_feature_matrix_reproduces_feature_coverage`,
`test_03_ap11_reproduces_campaign_manifest`) because they embed the
worktree path. They are NOT to be "fixed" in the lane; root re-runs the
full suite at the canonical path at integration.

## 8. Log

| Date | Change / next checkpoint | Evidence / open work |
| --- | --- | --- |
| 11.10.2026 | WP-18 plan | base `main` @ `55f1dcd` (0.10, after WP-17 integration); probe evidence in `side/evidence/` |
