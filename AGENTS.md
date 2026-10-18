# Project Handoff for Further Agents

**All repository documentation and workflow content is English-only
(2026-10-07, user decision).** Every doc, plan, ledger, tool message and
artifact string is maintained in English from now on, regardless of the
language used in chat.

**CT2Trainer (status 2026-10-18, 0.14 released with the 0.15 prefix-cut
field fix shipped on top (`d15268a`); Wave 3 of the reference-corpus
closure cycle complete on working branch `native-0.15` with all five
work packages (WP-37/38/39/40/41) merged; 0.9.0-rc2 was the last
user-tested release; working branch `native-0.15` tracks the
milestone):** the
repository is a
self-contained, clean-room development base for an independently designed,
source/binary-redistributable converter and trainer with **no CE
implementation inputs or binaries at all**. It was formerly named
"TrainerForge (Native)"; use CT2Trainer in all current code,
configuration, documentation and tooling.

Read first: the [central gap & goal tracking document](plans/TRACKING.md)
(single source of truth for all open gaps, goals, work packages, corpus
cases and the latest measurement snapshot), then the maintained
[continuation plan](plans/native-implementation-continuation.md) and the
[progress ledger](documentation/native-progress.md). They contain
the work packages, parallel ownership, resume commands and acceptance
criteria. Code/build boundaries: `documentation/native-runtime.md` and
`documentation/native-verification.md`. Build guide:
`documentation/build.md`.

Native builds run exclusively with **`scripts/Build-Native.ps1`** (fully
offline, hash-verified inputs from `dependencies/`). Local MIT/BSD forks,
adaptations and upstream API breaks are authorized; retain source pins,
notices, local changes and build evidence.

**CE behavior reference (2026-10-13, user decision):** the Cheat Engine 7.5
source tree at `C:\Users\xboxl\code\cheat-engine-7.5` (local-only, never
added to git) may be **read** to understand how CE handles a behavior
(offset parsing, `{$…}` directives, `return:` label scoping, phase
splitting, duplicate-ID tolerance, …). It is a **lookup/reference source
only**: no CE code is copied, derived, or ported into CT2Trainer — every
feature is re-implemented clean-room, and public API/format contracts may
be derived. All other CE implementation sources remain off-limits.

**Feature-matrix goal:** 100% coverage without AP-11. 42/42 in-scope
features covered (100% feature-weighted; 7426/7426
action-weighted; `gap_inventory/feature-coverage.json`, run
`w3e-case24-20261018051230`; the 2026-10-18 7416/7416 over
`w3d-case22-20261018040510`, the 2026-10-18 7413/7413 over
`w3b-case21-20261018023823Z`, the 2026-10-18 7411/7411 over
`w3-case23-20261018012531Z`, the 2026-10-16 7408/7408 over
`w2b-case18-20261016142912Z`, the 2026-10-15 7387/7387 over
`w2c-case15p2b-20261015144326Z`, the 2026-10-14 7381/7381 over
`w2a-case17-20261014112532Z`, the 2026-10-14 7376/7376 over
`w1a-case15-20261014011543Z`, the 2026-10-14 7371/7371 over
`w1a-case16-20261014003107Z`, the 2026-10-13 7369/7369 over
`w1e-case20-20261013234642Z`, the 2026-10-13 7365/7365 over
`w1d-case19-20261013192913Z`, the 2026-10-11 7361/7361 over
`wp14-staged-20261011T093320Z` and the 2026-10-10 39/39 over
`wpB-cleanroom4-20261010T104008Z` are superseded). The 90% hurdle and the
100% goal are reached and closed. All three gate features are closed with **real,
tested** evidence (2026-10-10):

1. `gate:1` – per-table completeness for all 24 pinned tables
   (Forms, Lua lifecycle, Custom Types, Assets):
   `tests/test_native_table_completeness.py` (every source record
   preserved; each table-level construct handled or surfaced fail-closed;
   synthetic embedded-Files case).
2. `gate:2` – Source-to-Frozen parity of the 0.9 feature set
   (`tests/test_native_source_frozen_parity.py`) + binary CLI/GUI adapter
   for the static IL2CPP parser:
   `src/ct2trainer/native/il2cpp_static_probe.py`, frozen launcher flags
   `--il2cpp-static-pe/--il2cpp-static-metadata/--il2cpp-static-report`,
   source CLI `ct2trainer native il2cpp`
   (`tests/test_native_il2cpp_static_probe.py`).
3. `gate:3` – end-to-end reproducibility chain across all features with
   exact commands and pinned inputs:
   `tests/test_native_repro_chain.py` (denominator -> feature matrix ->
   AP-11 manifest, byte-identical per fixed run-id).

Gate flips happen only with **real, tested** evidence; gate action weights
remain 0 (completeness/proof features, not record actions). The AP-11
campaign (6100 expected actions, 0 confirmed so far) remains a
**separate end goal** and is excluded from the 100% feature metric.

**Corpus:** `TableReferences/` is the synthetic clean-room corpus
(`case-01.ct` … `case-14.ct`, `case-15.ct`, `case-16.ct`,
`case-17.ct`, `case-18.ct`, `case-19.ct`, `case-20.ct`,
`case-21.ct`, `case-22.ct`, `case-23.ct`, `case-24.ct`; case-to-origin
mapping in `TableReferences/README.md`). `case-14.ct` is the WP-14
PRAGMATA behaviour derivative (staged capabilities, signed offsets,
activation sets). It is strictly read-only input; distributed releases
never contain original game tables.

**Distributed-release naming:** fresh builds produce
`CT2Trainer-<version>-source.zip` and
`CT2Trainer-<version>-windows-portable.zip` (version = content of the
root `VERSION` file); the binary plan footer magic is `CT2NATV1` and the
template stub marker is `CT2BASE1` (both 8 bytes). `TFSH0001` (one-shot
marker magic in `oneshot.json`, `one_shot_contract.py`) is intentionally
kept as a stable format constant — renaming would break existing user
state; it is documented, not a naming-debt item.

The build allowlist in `tools/native_build.py` (`source_files()` /
`RELEASE_DOC_FILES`) is the single source of truth for release content and
is verified by the in-build CE-content scan. Agent tooling (`AGENTS.md`,
`plans/`, `tools/agent_load.py` and the agent docs under `documentation/`)
is local-only by design and excluded from distributed ZIPs.

**Latest verified build:** `native-20261018T055505Z-39f20180` (0.15,
cut from `main` @ `ed0b97b`; in-build suite 3057 OK / 25 regular skips,
`ce_inputs: []`, `runtime_unverified` deliberately kept per gate; source
ZIP `CT2Trainer-0.15-source.zip` sha256
`5d5a85f63f0b0948b05e06bfba8f40fa91e7bf75e5d981da22b33a3a5f522581`,
portable ZIP `CT2Trainer-0.15-windows-portable.zip` sha256
`cfcc8e06f65d0b3c6ec1ef4671f2be520c45c1c6c85572f1dbe6e69d15ea8414`).
The 0.15 build adds the prefix-cut byte-patch validation (the
0.14-ext2 Great Circle field fix: `db 90 E9` over a 6-byte conditional
jump is now proven against the live target at link time and re-verified
at stage time, restoring the Stealth Mode and No Reload entries) and
the full Wave 3 feature set (per-record hotkeys, creator per-table
inspection, runtime dynamic address providers, read-only table-Lua
bootstrap with trainer banner, Lua-owned symbol handover with
teardown-order invariants) on top of the released 0.14 content; 24
pinned corpus tables, 6,100 AP-11 actions, weights 7,426/7,426 over
run `w3e-case24-20261018051230`; both ZIPs ship the elaborated release
READMEs (source: product overview + build guide; portable: full user
guide, including the debug-logging section) and the changelog with the
0.15 + 0.14 + 0.13 entries. Previous release build:
`native-20261017T115850Z-1ebb48b7` (0.14, cut from `main` @ `fca6b06`;
in-build suite 2932 OK / 25 regular skips; source ZIP sha256
`a5b075cf6535c5eef3807da7b7b9429dda08a3cf9f9dba6fdafb879e0dfce0a9`,
portable ZIP sha256
`e57fe9b9fb56ef7a97f81a98f04455976c4b5e9ebddee655b24cbb64e7ed3103`).
Earlier release build: `native-20261016T190005Z-b3139b30` (0.13, cut from
`main` @ `d57e62c`; in-build suite 2927 OK / 25 regular skips; source
ZIP sha256
`23b57307819e4262d8ca894ac16c86d595df9945c1afec25750f66bb9e0c9124`,
portable ZIP sha256
`d7f64efbae975f477e5bb011796d64276f32ef4300d4a0986961e95ae63aca78`).
Superseded 0.13 run: `native-20261016T181516Z-b8ae88de` (pre
module-snapshot fallback, cut from `main` @ `7184547`). Prior
release build: `native-20261016T163910Z-d047f2d2` (0.12, cut from
`main` @ `ba1d3e4`;
in-build suite 2910 OK / 25 regular skips; source ZIP sha256
`f5a5468da6e49ee5d4812dce3edea71e87e4bb9736ce4bf3486dfc0c66e70165`,
portable ZIP sha256
`7bd582e33f2978c641bb36a22ad8fc5f21bc9b695bb16930bed19720eaa81619`),
which contains the full Wave 2 set: W2-A (WP-27/32/33/34, merge
`aa6371b`), W2-C (WP-30/36, merge `32e0cdd`) and W2-B
(WP-28/29/31/35, merge `2f68f80`). Superseded 0.12 runs:
`native-20261016T161905Z-e8ef67a0` (byte-identical re-cut of the final
tree) and `native-20261016T154141Z-2de774ab` (pre release-docs update).
Superseded 0.11 run:
`native-20261012T092729Z-2d8aaf12` (0.11, cut from `main` @ `9a76eb8`;
in-build suite 2710 OK / 25 regular skips; source ZIP sha256
`168c14a452595588a6483140f1d43bec818d0f0d0e9eb72167453a80624469db`,
portable ZIP sha256
`8a2d6ac6f8b802714fe7578de54cea432506a41f8bf91d597a03fa086b04f196`).
Previous: `native-20261011T121914Z-bfc5fc11` (0.10, full WP-14 work,
in-build suite 2671 OK / 25 regular skips);
`native-20261010T172336Z-ffe35eb0` (0.9.0-rc2, in-build suite
2617 OK / 25 regular skips) was user-tested on a machine without CE or
Python (converter run plus generated trainer).

Workflow policy: each implementation cycle (milestone 0.9 and beyond)
runs on its own working branch (e.g. `native-0.9`); within a cycle, after
each integrated work package (or batch of lane integrations including
matrix flips and docs), the working branch is merged into `main` and
pushed again (normal merge + push, never force), so `main` continuously
tracks the milestone between cycle-end releases. `main` receives only
these release merges.

Subagent launch rule: before starting any new subagent lane, check the
model-server load with `tools/agent_load.py` (sglang metrics endpoint;
exit 0 = at least one lane may launch, 1 = defer). Launch new agents only
when the request queue is empty, the free KV span is substantial and the
abort counter is flat; under high load defer launches and advance
root-owned work in the meantime. Parallelize lanes up to the actual
capacity of the server so the available resources are used optimally;
never blindly launch into a saturated server. Lane contract:
`documentation/subagent-lane-rules.md`.

Read before any change:

1. [`README.md`](README.md) — quick start, provenance and current scope.
2. [`plans/native-implementation-continuation.md`](plans/native-implementation-continuation.md) — work packages and acceptance.
3. [`documentation/native-progress.md`](documentation/native-progress.md) — confirmed base, measured numbers and prioritized work.
4. [`documentation/native-runtime.md`](documentation/native-runtime.md) / [`native-verification.md`](documentation/native-verification.md) — code/build boundaries and proofs.
5. [`documentation/build.md`](documentation/build.md) — offline build, local test suite, release content rules.
6. [`documentation/native-semantic-denominator.md`](documentation/native-semantic-denominator.md) — pinned corpus tables and gap classes.
7. [`tests/deck/compatibility-matrix.md`](tests/deck/compatibility-matrix.md) — Proton/Steam Deck protocol, and [`tests/windows/fixture_target/README.md`](tests/windows/fixture_target/README.md) — the own Windows test target process.
8. [`documentation/subagent-lane-rules.md`](documentation/subagent-lane-rules.md) — parallel lane rules.

Confirmed product path: required inputs are a `.CT` file and the exact
game process EXE name; private own use. Saved enabled toggles are
automatically re-enabled after a successful re-attach. Only confirmed
ON-switches are persisted; a failed enable attempt stays visibly inactive
and is not repeated as a saved wish on the next attach. Final acceptance
is separate on Windows and on a real Steam Deck under Proton with touch
operation.

After new Windows or Deck tests, record the observed build — including
versions, hashes, test setup and result — in the documentation before
raising the status. Original-table Lua and Auto Assembler code may
execute when a generated trainer runs against its target; the local
tooling (converter, tests, corpus analysis) does not execute it.
