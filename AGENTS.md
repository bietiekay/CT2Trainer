# Project Handoff for Further Agents

**Start with the plain-language [current status](STATUS.md).** It summarizes
what is proven and what remains open; `plans/TRACKING.md` remains the
detailed source of truth. The root integrator must update `STATUS.md` in
the same change as `plans/TRACKING.md` and
`documentation/native-progress.md` whenever a package changes catalog or
feature-matrix counts, an AP-11/game or Windows/Deck observation is
recorded, or a build/release is cut. Record the evidence date, exact build
or source revision, input/run identifier and denominator. Keep synthetic
coverage, original-table static coverage and observed effect separate.
Do not report the reference-table goal as complete from the 42/42
synthetic matrix or carry stale counts into this overview.

**Active outcome (2026-10-26): 100% of the 151 local-only reference-table
paths (143 distinct hashes) must load and support their intended behavior
through an independent clean-room implementation.** The 0.16 Wave-4
feature work is complete; RT-4.1 (symbol provider fidelity) landed on
`main` 2026-10-22; RT-3 (legacy-binary CT loader; `SuperMeatBoy.CT`
now loads, table load 151/151) landed on `main` 2026-10-23; RT-4.4
(value semantics), RT-4.6 (input legacy & authoring gaps) and RT-4.5
(AA directive & script coverage) landed on `main` 2026-10-24; RT-4.3
(address expression & identifier dialect) landed on `main` 2026-10-26
(plus its dedicated dialect test follow-up); RT-4.2 (runtime provider
model: keep-first duplicate-provider scope fallback, mixed-dialect
unregistersymbol release evidence, bounded API-export registry with
link-time resolution) landed on `main` 2026-10-27, completing RT-4;
RT-5 item G
(createThread/threadWait gate decision, option 2: the capability gate
stays, no thread backend ships this milestone) and item F (no-effect
register ratification, tests only) landed on `main` 2026-10-26; RT-5
item A (embedded `<Files>` extraction: new `embedded_files.py`
dual-branch codec, fail-closed table-load decode, `findTableFile` /
`readStringLocal` / stringstream / stringlist Lua surface, +53 tests)
landed on `main` 2026-10-28 (merge `479977c`). The RT-5 API/construct
inventory is documented in `documentation/rt5-api-inventory.md`. The
latest original-table catalog (run `blocked-catalog-rt5a-main`,
2026-10-28, zero delta vs `blocked-catalog-rt42-main`) has 1,053 blocked
of 117,634 plan entries, 60,161 staged entries and zero load errors
(previous: 1,351 after RT-4.3, 1,743 after RT-4.5, 1,778 after RT-4.6,
1,807 after RT-4.4, 1,858 after RT-4.1/RT-3;
original baseline: 2,698 blocked, 58,950 staged). The 42/42 feature
matrix measures only the 30 pinned synthetic cases; AP-11 has 0/6,143
confirmed game effects. Read
[`plans/reference-table-100-roadmap.md`](plans/reference-table-100-roadmap.md)
for the active RT-1…RT-7 work and completion gates. Historical AP/WP
plans remain useful design records, not the current goal queue.
The requested parity scope is trainer/cheat handling and game-facing
effects; CE visual UI and editor features are outside scope unless a
table's UI API carries a game-facing action. The initial general
[capability assessment](documentation/ce-feature-parity-assessment.md)
records known gaps and the measurement method.

**All repository documentation and workflow content is English-only
(2026-10-07, user decision).** Every doc, plan, ledger, tool message and
artifact string is maintained in English from now on, regardless of the
language used in chat.

**CT2Trainer (status 2026-10-27, 0.17 released (build
`native-20261027T094839Z-ec6c6f55` cut from `main` @ `ee41630`;
previous 0.16.4 `native-20261024T003853Z-a8cf04fc` @ `988ff8e`,
previous 0.16.3 `native-20261023T065015Z-afbc3eba` @ `6a5ba63`, previous
0.16.2 `native-20261022T160328Z-0423fb21` @ `68eeb00`, previous
0.16.1 `native-20261021T161241Z-b0566a25` @ `d1c61f2`, previous
0.16 field-fix re-cut 2 `native-20261021T123801Z-8c5c4e1e` @ `108170b`,
re-cut 1 `native-20261020T150115Z-c426fb92` @ `7616edb` and first
0.16 run `native-20261020T103508Z-0e3f9d90` @ `809666a` superseded) with
the full Wave 4 feature set, RT-4.1 symbol provider fidelity (catalog
remeasure 2,698 -> 1,858 blocked of 117,624, zero unexplained supported
regressions), RT-4.4 value semantics (catalog remeasure
`blocked-catalog-rt44`: 1,858 -> 1,807 blocked of 117,634, zero newly
blocked rows) and the post-release field fixes (WP-58 UI
startup crash fix, Sinking City 2 activation-chain runtime evidence,
state-lock self-repair and reliable restart, SC2 startup-block
journal-field fix, SC2 activation field fix, SC2 crash-observability
field fix)
on top of the released 0.15 (prefix-cut field fix `d15268a`, part-3
fast-path fix `d068c44`); Wave 4 of the
reference-corpus closure cycle complete — all twelve W4 lanes
(WP-43/44/45/46p1/46p2/47/48/49/50/51/52/53/54/55/56/57 + WP-58 UI)
merged into `main` @ `0a38213`, cases 26/27/31 + 28/29/30 pinned
(30 pinned corpus tables, 6,143 AP-11 actions, weights
7,475/7,475 over run `w4b4-case30-20261020081722Z`); 0.9.0-rc2 was the
last user-tested release; `main` tracks the milestone between
releases):**
the
repository is a
self-contained, clean-room development base for an independently designed,
source/binary-redistributable converter and trainer with **no CE
implementation inputs or binaries at all**. It was formerly named
"TrainerForge (Native)"; use CT2Trainer in all current code,
configuration, documentation and tooling.

Read first: the [current status overview](STATUS.md), then the
[central gap & goal tracking document](plans/TRACKING.md)
(single source of truth for all open gaps, goals, work packages, corpus
cases and the latest measurement snapshot), then the active
[100% reference-table roadmap](plans/reference-table-100-roadmap.md) and the
[progress ledger](documentation/native-progress.md). They contain
the work packages, parallel ownership, resume commands and acceptance
criteria. The [earlier continuation plan](plans/archive/native-implementation-continuation.md)
preserves AP-01…AP-12 history. Code/build boundaries: `documentation/native-runtime.md` and
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
features covered (100% feature-weighted; 7475/7475
action-weighted; `gap_inventory/feature-coverage.json`, run
`w4b4-case30-20261020081722Z`; the 2026-10-19 7446/7446 over
`w4-case31-20261019061339`, the 2026-10-18 7426/7426 over
`w3e-case24-20261018051230`, the 2026-10-18 7416/7416 over
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

1. `gate:1` – per-table completeness for all 30 pinned tables
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
campaign (6143 expected actions, 0 confirmed so far) remains a
**separate end goal** and is excluded from the 100% feature metric.

**Corpus:** `TableReferences/` is the synthetic clean-room corpus
(`case-01.ct` … `case-14.ct`, `case-15.ct`, `case-16.ct`,
`case-17.ct`, `case-18.ct`, `case-19.ct`, `case-20.ct`,
`case-21.ct`, `case-22.ct`, `case-23.ct`, `case-24.ct`,
`case-26.ct`, `case-27.ct`, `case-28.ct`, `case-29.ct`,
`case-30.ct`, `case-31.ct`; case-to-origin
mapping in `TableReferences/README.md`). `case-14.ct` is the WP-14
PRAGMATA behaviour derivative (staged capabilities, signed offsets,
activation sets). It is strictly read-only input; distributed releases
never contain original game tables.

**Versioning rule (2026-10-21, user decision):** every build gets a
new version number. Feature releases bump the minor (0.16 → 0.17);
bug-fix builds bump the patch (0.16 → 0.16.1 → 0.16.2). Bump the root
`VERSION` file in the same change as the content change that triggers
the build, and add a `CHANGELOG.md` entry per shipped version.

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

**Latest verified build:** `native-20261027T094839Z-ec6c6f55` (0.17,
cut from `main` @ `ee41630`; in-build suite 3692 OK / 25 regular
skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per
gate; source ZIP `CT2Trainer-0.17-source.zip` sha256
`08af7d402df6380713f75cd270a27b9eb512e78a173d169ebd142f9411e65eee`
(13,162,166 bytes), portable ZIP
`CT2Trainer-0.17-windows-portable.zip` sha256
`ee6ad2ec4b72705b6a48f6631343c4caef1056f7bca5400ec0c5ebd8159ac15a`
(28,710,096 bytes)).
0.17 ships the RT-4.2 runtime provider model (last RT-4 package;
catalog remeasure `blocked-catalog-rt42-main`: 1,351 -> 1,053
blocked, 298 rows unblocked, zero newly blocked, 28 reason-only
changes) plus the RT-4.3 address-expression & identifier-dialect
merge, the RT-4.5 and RT-4.6 merges, the trainer UI Scripts view and
row context menu, and the RT-5 item G / F gate ratifications, on top
of the 0.16.4 content. Superseded 0.16.4 build: the
Sinking City 2 trainer-crash-observability field fix
(0.16.3 field test 2026-10-23: the windowed trainer process died
silently mid wish-restore - last event the TALENTPTR aobscan at
18:49:31, zero follow-up events - and the restart was blocked by the
correct state-lock refusal while the game was still running; every
Python-level failure path logs an event, so the silent death is a hard
exit, and the windowed build had no crash observability at all:
unattached stderr, no excepthook/faulthandler, unguarded Tk poll
callback) - `TrainerDebugLog.arm_crash_reporting()` installs one-time
process-wide `sys.excepthook` (`trainer-crashed` JSON event with full
traceback) and `threading.excepthook` (`trainer-thread-crashed`)
wrappers plus `faulthandler` on a dedicated append handle independent
of `close()`, `run_trainer` arms both entry points,
`TrainerWindow.poll` wraps `engine.poll()` fail-closed
(`poll-crashed` + engine block + tick continues), and the restore loop
logs `restore-entry-start` per wish before enable; state-lock
fail-closed behavior unchanged; regression test
`tests/test_native_sc2_crash_observability.py` +8) on top of the
0.16.3 content and the RT-4.4 value-semantics merge (catalog remeasure
`blocked-catalog-rt44`: 1,858 -> 1,807 blocked of 117,634, zero newly
blocked rows). Superseded 0.16.3 build:
`native-20261023T065015Z-afbc3eba` (0.16.3, cut from `main` @ `6a5ba63`;
in-build suite 3421 OK / 25 regular skips, `ce_inputs: []`,
`runtime_unverified` deliberately kept per gate; source ZIP
`CT2Trainer-0.16.3-source.zip` sha256
`0b34c4f3797095aefcba66a45d46216596e816817ea1b98208a42a5217df2e5a`
(13,050,549 bytes), portable ZIP
`CT2Trainer-0.16.3-windows-portable.zip` sha256
`bb495a6f61538051b8caeac14394bdc80b7b165b946f34f3ae710524e37fd0a3`
(28,609,768 bytes)).
0.16.3 ships the Sinking City 2 activation field fix (0.16.2 field
test 2026-10-22: the recovery assessment still rejected the WP-47/55
hook-journal `value_data_ranges` field on every allocation entry,
blocking startup behind a stale `state.lock` on every attempt; and
the module-snapshot retry targeted the wrong Win32 code -
`ERROR_BAD_LENGTH` mislabeled as 24, real 1116; 24 is
ERROR_INVALID_ID, the transient code observed 9 ms after attach while
the game was still loading DLLs; now a bounded 8-attempt
exponential-backoff retry on {1116, 24, 119}, architecture-aware
native-only fallback flag (0x10 for 32-bit targets), dual-failure
message carrying both codes; regression tests
`tests/test_native_architecture.py` +4 and
`tests/test_native_recovery.py` +2) on top of the 0.16.2 content.
Superseded 0.16.2 build:
`native-20261022T160328Z-0423fb21` (0.16.2, cut from `main` @
`68eeb00`; in-build suite 3415 OK / 25 regular skips, `ce_inputs:
[]`, user-tested, field finding: Sinking City 2 activation failure) -
the Sinking City 2 startup-block field fix (recovery assessment
accepts the WP-57 hook-journal `captured_placeholders` field;
regression tests `tests/test_native_recovery.py`) and RT-4.1 symbol
provider fidelity (keep-first duplicate-provider policy, `label()`
duplicate-name tolerance, wildcard-cleanup scoping; catalog remeasure
2,698 -> 1,858 blocked of 117,624, zero unexplained supported
regressions) on top of the 0.16.1 content. Superseded 0.16.1 build:
`native-20261021T161241Z-b0566a25` (0.16.1, first build under the new
versioning rule, cut from `main` @ `d1c61f2`; in-build suite 3412 OK /
25 regular skips, `ce_inputs: []`, user-tested, field finding: Sinking
City 2 startup block) — Sinking City 2 table-load warning fixes
(table-version reference 45 → 46 field-verified; `{$LUA}` warning
states the built-in Lua runtime path; external-action warning split
per API — ShellExecute safe no-op, messageDialog review flag) on top
of the 0.16 content, regression tests
`tests/test_native_sc2_table_warnings.py`.
0.16 ships the full Wave 4 feature set (WP-43…WP-57 + WP-58 UI, see
changelog) plus the post-release field fixes on top of the released 0.15
content (WP-58 UI startup crash: `_button` widget defaults merged into
the style dict + pagination tuple `padx` moved to `.pack()`, regression
test `tests/test_native_ui_button.py`; Sinking City 2 activation-chain
runtime evidence `tests/test_native_sc2_attach_chain.py`; state-lock
self-repair and reliable restart: close-after-blocked exit cleanup when
the target is gone, atexit session/lock release on a provably gone
target, actionable stale-lock refusal with assessment reasons and one
probe retry, regression tests
`tests/test_native_stale_lock_selfheal.py`); 30 pinned corpus tables,
6,143 AP-11 actions, weights 7,475/7,475 over run
`w4b4-case30-20261020081722Z`; both ZIPs carry the changelog with the
0.16 + 0.15 + 0.14 entries. Superseded 0.16 runs:
`native-20261021T141051Z-17d53c1d` (0.16, cut from `main` @ `e9f06fb`
after the RT-1 rebaseline; in-build suite 3405 OK / 25 regular skips,
`ce_inputs: []`; superseded by the 0.16.1 cut before its evidence was
recorded); `native-20261021T123801Z-8c5c4e1e` (0.16 field-fix re-cut 2,
cut from `main` @ `108170b`; in-build suite 3405 OK / 25 regular
skips, `ce_inputs: []`; user-tested, field finding: Sinking City 2
table-load warnings); `native-20261020T150115Z-c426fb92` (0.16 field-fix re-cut, cut from
`main` @ `7616edb`; in-build suite 3398 OK / 25 regular skips,
`ce_inputs: []`; source ZIP sha256
`35717144ed8c74fb1c690c8e692a0d53225b86401190b524715559bc13577ade`,
portable ZIP sha256
`24050f691603981ff0c33e2550adc885581a5131cd5a8123d0050618ca18178d`;
user-tested, field findings: one cheat = table/build mismatch, state-lock
orphan after a blocked close) and `native-20261020T103508Z-0e3f9d90`
(0.16, cut from `main` @ `809666a`; in-build suite 3393 OK / 25 regular
skips, `ce_inputs: []`; source ZIP
sha256 `370a2d73c597de283e4b0db9a7c5c8d68d542fba6d9516d9314c2bfc9cb1118e`,
portable ZIP sha256
`6db5bf69052767cf07529458c45d3f1c5f5089e8934c74ef2ce053b27dd23b8b`;
user-tested, shipped with the WP-58 UI startup crash). Previous release
build:
`native-20261018T055505Z-39f20180` (0.15, cut from `main` @ `ed0b97b`;
in-build suite 3057 OK / 25 regular skips, `ce_inputs: []`,
`runtime_unverified` deliberately kept per gate; source ZIP
`CT2Trainer-0.15-source.zip` sha256
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
2. [`plans/reference-table-100-roadmap.md`](plans/reference-table-100-roadmap.md) — active RT-1…RT-7 work packages and acceptance.
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
