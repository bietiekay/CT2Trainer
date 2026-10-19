#!/usr/bin/env python3
"""AP-10 lane tool: deterministic feature matrix and coverage metric for the 90% goal.

Read-only against the committed ``gap_inventory`` artifacts (this tool never
touches the corpus directory). It builds, in ``--output``:

  feature-coverage.json
    feature_matrix   one row per gap class (39) plus one row per
                     missing-gates entry; each row carries status
                     (covered | partial | missing), the dedicated
                     tests/test_native_*.py evidence files, the native
                     modules involved, the pinned affected-record weight
                     and an AP-11 exclusion flag
    ap11_exclusions  the missing_gates entries that are AP-11 game gates
                     (real game installs, observed game effect,
                     VM/Clean-PC, real Steam Deck with Proton prefix
                     incl. physical/touch input); excluded from every
                     coverage number
    coverage         feature-weighted and action-weighted coverage over
                     the non-AP-11 features only
    top10_priority   the ten most impactful still-open (partial/missing)
                     features by weighted action count
    consistency      cross-checks of the metric inputs against
                     gap-report.json and inventory.json

Status rules (static contract, documented per feature):
  covered  a dedicated existing tests/test_native_*.py file exercises the
           feature positively (or its fail-closed handling)
  partial  a module under src/ct2trainer exists but the feature is a
           stage-1 model without engine integration, fail-closed blocked,
           or lacks complete dedicated test coverage
  missing  nothing exists in the native source

AP-11 rule: the missing_gates entries that can only be satisfied on the
user's other machine are excluded from the coverage denominator; all 39
gap classes have an in-machine static/fixture verification path and stay
in scope.

Deterministic: same inputs + same run-id => byte-identical artifact (sorted
JSON keys, 1-space indent, no wall-clock timestamps; ``generated`` is the
documented run stamp ``"run <run-id>"``).

Exit codes: 0 ok + all consistency checks passed, 1 input error,
2 consistency failure (stale or damaged artifacts), 3 write refused
(never into the directory containing the input artifacts).

Usage:
  python tools/corpus_denominator/feature_matrix.py \
      [--gap-report <path>] [--inventory <path>] \
      --output <out-dir> [--run-id <id>] [--list]
"""
import argparse
import hashlib
import json
import os
import sys
from collections import Counter

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCHEMA_NAME = "corpus-feature-matrix/v1"
DEFAULT_RUN_ID = "repo-reproducible"

_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(_PKG_DIR))
DEFAULT_GAP_REPORT = os.path.join(REPO_ROOT, "gap_inventory", "gap-report.json")
DEFAULT_INVENTORY = os.path.join(REPO_ROOT, "gap_inventory", "inventory.json")

REQUIRED_REPORT_KEYS = (
    "generated", "lane", "counting_convention", "gap_labels",
    "pinned_tables", "corpus_rest", "denominator", "top_gaps_pinned",
)
REQUIRED_INVENTORY_KEYS = ("generated", "run_id", "tables", "totals",
                           "unique_table_count")

VALID_STATUSES = ("covered", "partial", "missing")

# ---------------------------------------------------------------------------
# AP-11 game-gate rules.
#
# The committed gap report lists hard ``missing_gates``. Four of them can
# only be satisfied on the user's other machine (real game installs,
# observed game effect, an isolated VM/Clean-PC, and a real Steam Deck with
# Proton prefix, which also covers physical/touch input observation). They
# are AP-11 game gates: features inside the product scope but excluded from
# the coverage denominator measured here. Matching is on stable ASCII
# substrings of the gate text (the report is UTF-8; umlauts are avoided).
# ---------------------------------------------------------------------------
AP11_GATE_RULES = (
    ("game installs",
     "AP-11: real game installs/builds of the pinned tables are only "
     "available on the user's machine; no in-machine proof exists."),
    ("game effect",
     "AP-11: actual observed game effect (ON/OFF, values, freeze, restarts) "
     "requires running the real game."),
    ("VM/Clean-PC",
     "AP-11: the isolated VM/clean-PC gate (portable start, UAC, debugger "
     "conflict) needs a dedicated machine without CE/Python."),
    ("Steam Deck with Proton",
     "AP-11: a real Steam Deck with Proton prefix, including physical "
     "Touch/Screenkeyboard input observation."),
)

# Non-AP-11 gates from the same missing_gates list: product features that
# are verifiable on this machine, kept in the matrix with a static status.
GATE_FEATURES = {
    "Table-level completeness": {
        "status": "covered",
        "evidence": ("tests/test_native_table_completeness.py",),
        "modules": ("src/ct2trainer/native/compiler.py",
                    "src/ct2trainer/table.py"),
        "note": "Demonstrated for all 27 pinned tables: every source "
                "record is preserved (no silent drops), and each table-level "
                "construct — Forms, the table-Lua lifecycle, Custom types and "
                "embedded Assets — is handled or surfaced fail-closed "
                "(ignored_sections / lua_bootstrap / blocked-with-reason). A "
                "synthetic embedded-Files case proves the Assets path.",
    },
    "Frozen/binary proof": {
        "status": "covered",
        "evidence": ("tests/test_native_build_boundary.py",
                     "tests/test_native_global_probe.py",
                     "tests/test_native_source_frozen_parity.py",
                     "tests/test_native_il2cpp_static_probe.py"),
        "modules": ("tools/native_build.py",
                    "src/ct2trainer/native/global_probe.py",
                    "src/ct2trainer/native/launcher.py",
                    "src/ct2trainer/native/il2cpp_static_probe.py"),
        "note": "Frozen trainers build from a checked independent template "
                "and the Frozen-Global probe gate (byte-pinned acceptance, "
                "owned-target admission, 14/14 report on x64/x86) is "
                "tested. Source-to-Frozen parity of the 0.9 feature set is "
                "proven by round-tripping real corpus plans through "
                "build_trainer/read_embedded_plan (value- and canonical-"
                "byte-identical, launcher-smoke validated). The static "
                "IL2CPP parser now has a binary CLI adapter: the frozen "
                "launcher exposes --il2cpp-static-pe/--il2cpp-static-"
                "metadata/--il2cpp-static-report and the source CLI exposes "
                "`ct2trainer native il2cpp`, both producing a bounded, "
                "read-only report with no process access or target writes.",
    },
    "Reproducibility": {
        "status": "covered",
        "evidence": ("tests/test_native_corpus_traceability.py",
                     "tests/test_native_repro_chain.py"),
        "modules": ("tools/corpus_denominator",),
        "note": "Pinned inputs and deterministic tooling: the full chain "
                "(denominator -> feature matrix -> AP-11 manifest) is "
                "reproducible byte-for-byte for a fixed run-id, and the "
                "committed gap_inventory artifacts are exactly reproduced "
                "from the committed corpus (test_native_repro_chain.py).",
    },
}

# ---------------------------------------------------------------------------
# Static feature contract: one entry per gap class from
# gap-report.json -> gap_labels (39). Each entry fixes the deterministic
# status, the dedicated tests/test_native_*.py evidence files, the native
# modules involved and a note. Paths are repo-relative POSIX. The
# consistency section verifies that this contract covers exactly the
# report's gap_labels set and that every cited path exists in the repo.
# ---------------------------------------------------------------------------
FEATURES = {
    "aa_conditional_block": {
        "status": "covered",
        "evidence": ("tests/test_native_aa_blocks.py",
                     "tests/test_native_aa_conditional_block.py"),
        "modules": ("src/ct2trainer/native/aa_blocks.py",
                    "src/ct2trainer/native/aa_program.py",
                    "src/ct2trainer/native/lua_program.py"),
        "note": "Deterministic {$if}/{$else}/{$endif} conditional pruning "
                "with {$define NAME LITERAL} macros (decimal, $hex, 0x hex, "
                "optional sign; casefolded names, single definition per "
                "name) is now wired into prepare_program: the four "
                "directive lines pass _clean_source as whole lines, are "
                "collected before per-line parsing, and are pruned by the "
                "tested aa_blocks.prune_conditionals whose decisions and "
                "original line numbers are remapped into the byte-"
                "verifiable program fields defines and "
                "conditional_decisions; both plan validators re-derive and "
                "byte-check them, and mixed Lua+AA records reach "
                "prepare_program through the Lua _AALex. All other {$...} "
                "forms stay refused fail-closed (surface pinned in "
                "test_native_assembler.py); live-target execution is "
                "open (AP-11).",
    },
    "aa_createthread_threadwait": {
        "status": "covered",
        "evidence": ("tests/test_native_aa_directives.py",
                     "tests/test_native_aa_directive_wiring.py"),
        "modules": ("src/ct2trainer/native/aa_directives.py",
                    "src/ct2trainer/native/aa_program.py",
                    "src/ct2trainer/native/engine.py",
                    "src/ct2trainer/native/lua_activation.py"),
        "note": "The active pipeline now executes createThread(addr)/"
                "threadWait(): prepare_program parses the bounded node and "
                "reports it via capabilities; preflight resolves the "
                "address and executes spawn + deterministic completion "
                "polls through the injected ThreadDirectiveModel exactly "
                "once (execute_side_effects gate: the engine preflight "
                "executes enable-section side effects, the enable link and "
                "the dry link never re-execute, the inverse disable link "
                "executes disable-section ops exactly once on the shared "
                "model); the engine gates activation on an injectable "
                "thread backend (the default route refuses visibly "
                "fail-closed before any allocation or write; the owned "
                "Windows CreateRemoteThread route is open, AP-11) and "
                "records without the capability never touch the factory. "
                "Live-target execution remains open (AP-11).",
    },
    "aa_debugger_api": {
        "status": "covered",
        "evidence": ("tests/test_native_aa_directives.py",
                     "tests/test_native_iced_disassembler.py",
                     "tests/test_native_aa_disassemble_wiring.py"),
        "modules": ("src/ct2trainer/native/aa_directives.py",
                    "src/ct2trainer/native/iced_disassembler.py",
                    "src/ct2trainer/native/aa_program.py",
                    "src/ct2trainer/native/engine.py",
                    "src/ct2trainer/native/lua_activation.py"),
        "note": "The active pipeline now executes disassemble(addr, "
                "count): prepare_program parses the bounded node "
                "(1-4096 instructions) and reports it via capabilities; "
                "preflight/dry_link run the bounded read-only inspection "
                "through the injected DisassemblerPort (default: owned "
                "iced-x86 1.21.0 backend bound to the linked memory, with "
                "module-boundary probe fallback) and return it as an "
                "observation; the engine gates activation on the port "
                "(visible fail-closed refusal without one) and records "
                "without the capability never touch the factory. "
                "Live-target evidence remains open (AP-11).",
    },
    "aa_directive_unverified": {
        "status": "covered",
        "evidence": ("tests/test_native_assembler.py",
                     "tests/test_native_compiler.py"),
        "modules": ("src/ct2trainer/native/aa.py",
                    "src/ct2trainer/native/aa_program.py",
                    "src/ct2trainer/native/assembler.py"),
        "note": "Unknown residual directive tokens are rejected fail-closed "
                "by the owned AA grammar and linker.",
    },
    "aa_globalalloc_general": {
        "status": "covered",
        "evidence": ("tests/test_native_global_alloc.py",
                     "tests/test_native_global_engine.py",
                     "tests/test_native_global_strings.py",
                     "tests/test_native_global_recovery.py",
                     "tests/test_native_global_general.py"),
        "modules": ("src/ct2trainer/native/global_alloc.py",
                    "src/ct2trainer/native/global_probe.py",
                    "src/ct2trainer/native/engine.py"),
        "note": "Beyond the adopted literal-only path, the pinned Fallout 4 "
                "staged readmem shape compiles and executes: an ENABLE-phase "
                "readmem under the direct global cursor stages a "
                "target-to-global copy executed before the consumer install "
                "(AOB symbols resolved from the scan capture) under the "
                "capture recheck, and a DISABLE-phase readmem under a target "
                "cursor stages a global-to-target restore executed after the "
                "consumer patch is reverted but before the lease is released; "
                "staged lines are stripped from the consumer source so the "
                "byte-equality bind holds, staged ranges are exempted "
                "fail-closed from the consumer-side restore check, empty-"
                "initializer globals publish through an allocation-only "
                "HookManager commit, and unpaired readmem, global-referencing "
                "assert/reassemble, oversized copies, initializer mixing and "
                "scan drift stay refused. The Trine literal-only shape stays "
                "byte-identical. Live-target execution remains open (AP-11).",
    },
    "aa_luacall": {
        "status": "covered",
        "evidence": ("tests/test_native_aa_luacall.py",
                     "tests/test_native_aa_luacall_wiring.py",
                     "tests/test_native_compiler.py"),
        "modules": ("src/ct2trainer/native/aa_luacall.py",
                    "src/ct2trainer/native/compiler.py",
                    "src/ct2trainer/native/engine.py"),
        "note": "The tested Stage-1 static luaCall plan model (single-line "
                "call grammar with the pinned escape set, integer and simple "
                "decimal number arguments, lua_aobscan/ct2trainerNthAOB "
                "recognition with Nth-AOB pattern normalization and "
                "occurrence bounds, per-phase operations with line context, "
                "one-shot detection, injectable binding contract) is now "
                "active in the pipeline: compile_table embeds the "
                "deterministic lua_call_plan into pure-AA records whose "
                "luaCall lines match the grammar; expressions outside the "
                "grammar (multi-statement bodies, function definitions, "
                "{$lua} mode sections) keep the existing Lua program profile "
                "path without a plan, so prior behavior is preserved; the "
                "engine gates record activation behind an injected "
                "LuaCallBinding (function-name coverage and the AOB port) "
                "and fails closed with a visible named refusal before any "
                "publication; embedded plans are re-validated at engine "
                "start. Live-target execution of the six pinned corpus "
                "records and an owned AOB host binding remain open (AP-11).",
    },
    "aa_nested_script": {
        "status": "covered",
        "evidence": ("tests/test_native_aa_blocks.py",
                     "tests/test_native_aa_nested_script.py"),
        "modules": ("src/ct2trainer/native/aa_blocks.py",
                    "src/ct2trainer/native/aa_program.py",
                    "src/ct2trainer/native/compiler.py"),
        "note": "The active AA pipeline resolves nested assembly "
                "invocations (autoAssemble/autoasm) through the tested "
                "Stage-1 resolver: label definitions, an optional "
                "table-level label registry, deterministic topological "
                "inlining (callee before caller), unknown/collision/"
                "duplicate/cycle refusals with visible line context, and "
                "additive plan metadata (nested_invocations, "
                "nested_label_order, external_labels) re-derived and "
                "byte-verified by both plan validators. Label bodies "
                "(internal spans and external registry entries) must not "
                "contain [ENABLE]/[DISABLE] section markers; ambiguous "
                "table-level names are refused fail-closed; programs "
                "without nested invocations keep the exact pre-wiring "
                "plan shape. Live-target execution of AA-directive "
                "nested scripts remains open (AP-11; the pinned corpus "
                "uses the Lua-level autoAssemble form handled by the "
                "Lua pipeline).",
    },
    "aa_protection_control": {
        "status": "covered",
        "evidence": ("tests/test_native_hooks.py", "tests/test_native_scan.py",
                     "tests/test_native_aa_directives.py",
                     "tests/test_native_aa_directive_wiring.py"),
        "modules": ("src/ct2trainer/native/hooks.py",
                    "src/ct2trainer/native/memory.py",
                    "src/ct2trainer/native/aa_directives.py",
                    "src/ct2trainer/native/aa_program.py",
                    "src/ct2trainer/native/engine.py",
                    "src/ct2trainer/native/lua_activation.py"),
        "note": "Guard-page allocation safety is owned and tested; the "
                "active pipeline now executes protect/unprotect: "
                "prepare_program parses the bounded node (PAGE_* name or "
                "integer page constant, 1-0x1000000 byte size) and "
                "reports it via capabilities; preflight resolves the "
                "address and applies/releases through the injected "
                "ProtectionDirectiveModel (exact PAGE_* constants, page "
                "alignment, boundary and foreign-overlap refusals, "
                "idempotent protect, unprotect-warning) with one model "
                "shared across preflight/enable link/inverse disable link "
                "so the disable-section unprotect matches the "
                "enable-section protect state; the engine gates activation "
                "on an injectable protection backend (the default route "
                "refuses visibly fail-closed before any allocation or "
                "write; the owned Windows VirtualProtect route is open, "
                "AP-11). Live-target execution remains open (AP-11).",
    },
    "aa_sections_incomplete": {
        "status": "covered",
        "evidence": ("tests/test_native_compiler.py",
                     "tests/test_native_lua_eof.py",
                     "tests/test_native_aa_directives.py"),
        "modules": ("src/ct2trainer/native/aa.py",
                    "src/ct2trainer/native/aa_program.py",
                    "src/ct2trainer/native/lua_program.py"),
        "note": "Missing/empty ENABLE-DISABLE sections are rejected "
                "fail-closed by the active pipelines: prepare_program "
                "requires exactly one [ENABLE] followed by one [DISABLE] "
                "(duplicates, out-of-order markers, missing markers, empty "
                "[ENABLE] and EOF after [ENABLE] raise named errors; an "
                "empty [DISABLE] is the documented one-shot exception) and "
                "the small aa.compile_script byte-patch language rejects "
                "content-dependently through its symmetric-patch guard "
                "(symbol-only scripts are the documented positive "
                "exception); the tested structural model "
                "(analyze_sections/check_sections with GRAMMAR_FULL/"
                "GRAMMAR_SMALL) mirrors this exact rejection surface as a "
                "pinned negative model, and no-op, EOF-boundary and "
                "missing-[DISABLE] record-level refusals are pinned "
                "end-to-end through compile_table with visible block "
                "reasons. Live-target execution is open (AP-11).",
    },
    "aa_target_api_binding": {
        "status": "covered",
        "evidence": ("tests/test_native_pe_exports.py",
                     "tests/test_native_aa_directives.py",
                     "tests/test_native_aa_directive_wiring.py"),
        "modules": ("src/ct2trainer/native/pe_exports.py",
                    "src/ct2trainer/native/memory.py",
                    "src/ct2trainer/native/aa_directives.py",
                    "src/ct2trainer/native/aa_program.py",
                    "src/ct2trainer/native/engine.py",
                    "src/ct2trainer/native/lua_activation.py"),
        "note": "Remote PE export resolution is tested and integrated into "
                "ProcessMemory; the active pipeline now executes "
                "getmodulehandle(\"module\") / getprocaddress(\"module\","
                "\"export\") as read-only preflight observations (named and "
                "ordinal exports, forwarders flagged forwarded=true, "
                "missing-export refusals with module/export context). The "
                "default route is the read-only resolver bound to the "
                "linked memory itself (bounded read + module identity); an "
                "injected export backend factory may replace it or refuse "
                "visibly fail-closed. Identical repeated calls are "
                "deduplicated across the preflight re-runs of one install. "
                "Live-target invocation remains open (AP-11).",
    },
    "address_form_unrecognized": {
        "status": "covered",
        "evidence": ("tests/test_native_addresses.py",
                     "tests/test_native_compiler.py"),
        "modules": ("src/ct2trainer/native/address_expression.py",),
        "note": "Address-expression parser with explicit bounds; "
                "unrecognized forms are rejected fail-closed.",
    },
    "async_lifecycle": {
        "status": "covered",
        "evidence": ("tests/test_native_activation_policy.py",
                     "tests/test_native_compiler.py",
                     "tests/test_native_async_lifecycle.py"),
        "modules": ("src/ct2trainer/native/activation_policy.py",
                    "src/ct2trainer/native/compiler.py",
                    "src/ct2trainer/native/engine.py",
                    "src/ct2trainer/native/parent_flags.py"),
        "note": "Stage-1 parent/async policy model is tested (confirm/"
                "cancel/late completion, async requires confirmed attach); "
                "the compiler accepts async-marked records with their "
                "regular profile plus a plan-level async marker (both "
                "plan validators reject malformed markers); the engine "
                "routes async records through the controller with "
                "attach-gated request/dispatch/publish and generation-"
                "pinned confirm, observational before/after-effect "
                "classification that fails closed to a safety hold on "
                "uncertain partial effects, wish persistence in the "
                "desired set (confirmed ON only), replay on re-attach "
                "and drain on detach/close (slice B, 15 dedicated "
                "engine lifecycle tests).",
    },
    "cross_record_symbol": {
        "status": "covered",
        "evidence": ("tests/test_native_compiler.py",
                     "tests/test_native_global_strings.py",
                     "tests/test_native_addresses.py",
                     "tests/test_native_staged_capability.py"),
        "modules": ("src/ct2trainer/native/compiler.py",
                    "src/ct2trainer/native/engine.py",
                    "src/ct2trainer/native/aa.py",
                    "src/ct2trainer/native/lua_symbol_providers.py"),
        "note": "Static provider dependency closure in the compiler plus "
                "runtime symbol resolution in the engine (the owned-global "
                "fixtures bind a value record to a symbol of another "
                "record). WP-14 adds staged runtime gating on top: a "
                "supported record whose required symbols are all uniquely "
                "provided by supported providers carries staged plan "
                "metadata (provider IDs and labels), and the engine gates "
                "value read/write/freeze on provider liveness (named "
                "fail-closed error while the provider is off; freeze "
                "released when the provider deactivates).",
    },
    "custom_type": {
        "status": "covered",
        "evidence": ("tests/test_native_custom_types.py",
                     "tests/test_native_custom_type_runtime.py",
                     "tests/test_native_custom_type_wiring.py"),
        "modules": ("src/ct2trainer/native/custom_types.py",
                    "src/ct2trainer/native/custom_type_runtime.py"),
        "note": "Static custom-type codecs, write gate and table/compiler/"
                "lua_host wiring (adopted 0.8).",
    },
    "dropdown_link": {
        "status": "covered",
        "evidence": ("tests/test_native_compiler.py",
                     "tests/test_native_dropdown_link.py",
                     "tests/test_native_value_links.py"),
        "modules": ("src/ct2trainer/native/compiler.py",
                    "src/ct2trainer/native/engine.py",
                    "src/ct2trainer/native/value_links.py"),
        "note": "Cross-record DropDownListLink compiles (target "
                "resolution, borrowed literal choices, read-only "
                "inheritance, missing/ambiguous/chained refusals); the "
                "plan records the target explicitly via "
                "dropdown.link_target_id and both plan validators "
                "refuse forged targets. Runtime writes the choice "
                "literal to the linked record's own address through "
                "its own value profile (corpus/CE parity; own-address "
                "read-back and freeze tested on the pinned rml shape "
                "and a borrowed-choice shape). The owned stage-1 "
                "binding model in value_links (zero-based index "
                "semantics, byte-exact apply plans to a value-record "
                "target) remains tested as the value-target variant. "
                "AP-11 in-game effect stays open.",
    },
    "lua_ce_engine_api": {
        "status": "covered",
        "evidence": ("tests/test_native_lua_engine_api.py",),
        "modules": ("src/ct2trainer/native/lua_host.py",),
        "note": "getLuaEngine()/GetLuaEngine() returns an owned, closed "
                "trainer-engine facade (close, attached, processName, "
                "MenuItemN.doClick/clickMenuItem via owned menu-action "
                "registry); shutdown/menu routes are owner-injected and "
                "fail closed without them (adopted 0.9).",
    },
    "lua_clock_speed": {
        "status": "covered",
        "evidence": ("tests/test_native_clock_engine.py",
                     "tests/test_native_clock.py",
                     "tests/test_native_lua_clock.py"),
        "modules": ("src/ct2trainer/native/clock_engine.py",
                    "src/ct2trainer/native/clock_binding.py",
                    "src/ct2trainer/native/engine.py",
                    "src/ct2trainer/native/lua_host.py"),
        "note": "The corpus speed surface (speedhack_setSpeed / "
                "speedhack_getSpeed, pinned by the Alien Isolation and re2 "
                "records) is routed in the Lua host profile through the "
                "tested Clock v2 core/gateway model: the per-attach "
                "clock_binding.ClockSpeedBinding wraps ClockCore plus "
                "ClockGateway with an owner-scoped lease renewed inside "
                "tick(), maps the multiplier to ppm via "
                "round(speed * RATE_ONE), enforces the visible x16 "
                "profile limit with x20 refused visibly (never clamped "
                "silently), and every refusal is named and effect-free "
                "(ClockNotAttached, ClockTerminated, ClockBadMultiplier, "
                "ClockRateOutOfRange, ClockFault); tick() never raises "
                "into the poll loop and finish() is total. The engine "
                "creates the binding per confirmed attach through an "
                "injectable clock_factory (the default binding refuses "
                "visibly), ticks it in the connected branch, and retires "
                "it on confirmed target exit and both close paths. The "
                "owned real Windows clock API (timeBeginPeriod route) "
                "remains open (AP-11); setMulti/getMulti stay open "
                "(no pinned records).",
    },
    "lua_debugger_api": {
        "status": "covered",
        "evidence": ("tests/test_native_debug_coordinator.py",
                     "tests/test_native_lua_debugger_api.py"),
        "modules": ("src/ct2trainer/native/debug_coordinator.py",
                    "src/ct2trainer/native/debugger_session.py",
                    "src/ct2trainer/native/engine.py",
                    "src/ct2trainer/native/lua_host.py"),
        "note": "The Lua-facing attachProcess/detachProcess surface is now "
                "wired through the engine: the engine owns at most one "
                "session binding per attached target, created lazily "
                "through the injected debugger_factory and retired on "
                "confirmed target exit and close; attachProcess must "
                "target the attached game process and the binding pid is "
                "cross-checked before adoption; the tested "
                "DebugEventCoordinator stays the scoped quiescence owner. "
                "The default route (no factory) refuses visibly fail-closed "
                "because the persistent owned Windows debug attach route is "
                "open (AP-11); the pinned corpus carries 0 debugger "
                "records, so no denominator change.",
    },
    "lua_dynamic_assembler": {
        "status": "covered",
        "evidence": ("tests/test_native_lua.py",),
        "modules": ("src/ct2trainer/native/lua_host.py",),
        "note": "autoAssemble() is part of the owned host profile with "
                "receipt-based results.",
    },
    "lua_gui_api": {
        "status": "covered",
        "evidence": ("tests/test_native_ui_layout.py",
                     "tests/test_native_ui_tone.py",
                     "tests/test_native_lua.py"),
        "modules": ("src/ct2trainer/native/ui.py",
                    "src/ct2trainer/native/ui_layout.py",
                    "src/ct2trainer/native/lua_host.py"),
        "note": "showMessage/Forms surface in the owned host profile; the "
                "touch UI layout contract and tone playback are tested.",
    },
    "lua_host_profile": {
        "status": "covered",
        "evidence": ("tests/test_native_lua.py",
                     "tests/test_native_lua_bootstrap.py",
                     "tests/test_native_lua_program.py",
                     "tests/test_native_lua_eof.py",
                     "tests/test_native_lua_work_budget.py"),
        "modules": ("src/ct2trainer/native/lua_host.py",
                    "src/ct2trainer/native/lua_program.py",
                    "src/ct2trainer/native/lua_bootstrap.py"),
        "note": "Owned Lua 5.3 host with the bounded CE-Lua API profile, "
                "static bootstrap profiles and work budgets.",
    },
    "lua_managed_runtime": {
        "status": "covered",
        "evidence": ("tests/test_native_mono_broker.py",
                     "tests/test_native_mono_runtime.py",
                     "tests/test_native_mono_sources.py",
                     "tests/test_native_lua_managed_runtime.py"),
        "modules": ("src/ct2trainer/native/mono_broker.py",
                    "src/ct2trainer/native/mono_runtime.py",
                    "src/ct2trainer/native/mono",
                    "src/ct2trainer/native/managed_session.py",
                    "src/ct2trainer/native/engine.py",
                    "src/ct2trainer/native/lua_host.py"),
        "note": "The tested Mono stack (broker stage 1, runtime stage 2) is "
                "now wired into the engine and the Lua host: "
                "LaunchMonoDataCollector / mono_enumDomains / mono_findMethod / "
                "mono_invoke_method route to TrainerEngine managed_* facades that "
                "own at most one managed session per attached target, created "
                "lazily through the injected managed_runtime_factory and retired "
                "on confirmed target exit and close (target_ended / release, "
                "never raising into poll/close). The reference session drives "
                "the tested MonoRuntime (one frozen bootstrap, fresh one-shot "
                "tokens, reversible undo-receipt rule, vt-to-arg-kind mapping) "
                "with visible fail-closed refusals for identity mismatch, "
                "wrong-domain, malformed values and unknown terminal outcomes; "
                "without a configured binding the default route refuses visibly "
                "fail-closed. Actual adapted Mono calls against a live target "
                "remain an AP-11 gate.",
    },
    "lua_process_api": {
        "status": "covered",
        "evidence": ("tests/test_native_lua_process_api.py",),
        "modules": ("src/ct2trainer/native/lua_host.py",
                    "src/ct2trainer/native/memory.py"),
        "note": "getProcHandle/getOpenProcessID are owned read-only reads "
                "of the attached session target "
                "(ProcessMemory.process_handle); OpenProcess (new handle "
                "creation) stays outside the profile fail-closed; "
                "trainer-side process detection is a separate feature "
                "(adopted 0.9).",
    },
    "lua_record": {
        "status": "covered",
        "evidence": ("tests/test_native_lua_record.py",),
        "modules": ("src/ct2trainer/native/lua_host.py",
                    "src/ct2trainer/native/lua_activation.py",
                    "src/ct2trainer/native/engine.py"),
        "note": "Phase-selected Lua records share exact owned undo with AA "
                "(engine integration tested).",
    },
    "lua_record_body": {
        "status": "covered",
        "evidence": ("tests/test_native_lua_record.py",
                     "tests/test_native_lua_activation.py"),
        "modules": ("src/ct2trainer/native/lua_activation.py",
                    "src/ct2trainer/native/lua_program.py"),
        "note": "Lua bodies on records run through owned callbacks with "
                "durable receipts that survive failures.",
    },
    "lua_symbol_api": {
        "status": "covered",
        "evidence": ("tests/test_native_lua.py",
                     "tests/test_native_lua_symbol_api.py"),
        "modules": ("src/ct2trainer/native/lua_host.py",
                    "src/ct2trainer/native/lua_activation.py"),
        "note": "registerSymbol/unregisterSymbol plus strict "
                "getAddressOfSymbol (raises) and getAddressOfSymbolSafe "
                "(None) casefolded lookups are in the owned host profile, "
                "read-only during helper bootstrap (adopted 0.9).",
    },
    "lua_typed_target_call": {
        "status": "covered",
        "evidence": ("tests/test_native_call_broker.py",
                     "tests/test_native_target_broker.py",
                     "tests/test_native_lua_typed_target_call.py"),
        "modules": ("src/ct2trainer/native/call_broker.py",
                    "src/ct2trainer/native/target_broker",
                    "src/ct2trainer/native/typed_call.py",
                    "src/ct2trainer/native/lua_host.py"),
        "note": "executeCodeEx routes through the tested call_broker/target_broker "
                "foundation via the engine-owned typed_call binding (injected "
                "call_broker_factory, created at attach, retired at exit/close, "
                "identity-checked against the attached target); the CE call shape "
                "maps to the two-integer-word CDECL_ADD wire operation, and "
                "refusals (not attached, contract, busy, refused, uncertain) are "
                "named fail-closed errors. AP-11 live-target execution and a "
                "product-injected real broker backend remain open.",
    },
    "lua_worker_thread": {
        "status": "covered",
        "evidence": ("tests/test_native_lua.py",
                     "tests/test_native_lua_work_budget.py"),
        "modules": ("src/ct2trainer/native/lua_host.py",),
        "note": "createThread() runs on the owned cooperative scheduler "
                "with worker limits and terminate semantics.",
    },
    "managed_method_resolution": {
        "status": "covered",
        "evidence": ("tests/test_native_il2cpp_static.py",
                     "tests/test_native_il2cpp_live.py",
                     "tests/test_native_il2cpp_host.py",
                     "tests/test_native_managed_method.py"),
        "modules": ("src/ct2trainer/native/il2cpp_static.py",
                    "src/ct2trainer/native/il2cpp_live.py",
                    "src/ct2trainer/native/il2cpp_host.py",
                    "src/ct2trainer/native/address_expression.py",
                    "src/ct2trainer/native/aa_program.py",
                    "src/ct2trainer/native/engine.py"),
        "note": "AA injection labels (Class:Method and "
                "Namespace.Class.Method) compile into program "
                "managed_method_labels, never into requires; the engine "
                "resolves them through the injected IL2CPP resolver "
                "(tested stage-2 registration host) per program install "
                "and links byte-exact patches at the proven live address, "
                "fail-closed without a resolver. Real module acquisition "
                "(pinned Unity files, CodeRegistration) and in-game "
                "effect stay open (AP-11).",
    },
    "one_shot_save_contract": {
        "status": "covered",
        "evidence": ("tests/test_native_compiler.py",
                     "tests/test_native_state_takeover.py",
                     "tests/test_native_stale_lock.py",
                     "tests/test_native_one_shot_contract.py",
                     "tests/test_native_one_shot_wiring.py",
                     "tests/test_native_auto_on_attach.py"),
        "modules": ("src/ct2trainer/native/aa.py",
                    "src/ct2trainer/native/aa_program.py",
                    "src/ct2trainer/native/lua_program.py",
                    "src/ct2trainer/native/compiler.py",
                    "src/ct2trainer/native/engine.py",
                    "src/ct2trainer/native/one_shot_contract.py"),
        "note": "Fail-closed ENABLE/DISABLE gate, the adopted one-shot "
                "contract model (phase machine, save-only-after-confirmed-"
                "ON, OFF without backend effect, once-per-attach replay, "
                "marker codec) and the compiler/engine wiring are tested: "
                "classification, plan flags, bounded publish backend, "
                "marker persistence, attach replay, auto-on from "
                "disconnected state with pending one-shot wishes, and the "
                "auto-on cancel path.",
    },
    "parent_activation": {
        "status": "covered",
        "evidence": ("tests/test_native_activation_policy.py",
                     "tests/test_native_compiler.py",
                     "tests/test_native_parent_activation.py",
                     "tests/test_native_engine.py"),
        "modules": ("src/ct2trainer/native/activation_policy.py",
                    "src/ct2trainer/native/parent_flags.py",
                    "src/ct2trainer/native/compiler.py",
                    "src/ct2trainer/native/engine.py"),
        "note": "Flagged group headings route through the tested "
                "ActivationController (ON top-down, OFF bottom-up, "
                "moBindActivation named refusal, safety holds, save "
                "boundary, attach replay, mirror of engine state); "
                "22 dedicated tests in test_native_parent_activation.py.",
    },
    "record_activation_set": {
        "status": "covered",
        "evidence": ("tests/test_native_activation_sets.py",
                     "tests/test_native_compiler.py"),
        "modules": ("src/ct2trainer/native/lua_activation_sets.py",
                    "src/ct2trainer/native/compiler.py",
                    "src/ct2trainer/native/engine.py"),
        "note": "The converter statically extracts record-ID enable/disable "
                "sets from embedded {$lua} blocks (narrow grammar: one "
                "getMemoryRecordByID(<id>).Active = true|false line per "
                "record ID, uniform direction per section, every ID must "
                "exist; any ambiguity fails closed without metadata). "
                "Toggling such a record applies the set through the "
                "engine's dependency-ordered per-record activation path "
                "instead of executing the CE-coupled Lua; both plan "
                "validators re-derive and refuse tampered sets. Corpus "
                "case-14 pins the master-toggle shape (async record 0, "
                "set {2,6,8,11,14,25}).",
    },
    "record_unclassifiable": {
        "status": "covered",
        "evidence": ("tests/test_native_compiler.py",),
        "modules": ("src/ct2trainer/native/compiler.py",
                    "src/ct2trainer/table.py"),
        "note": "Unclassifiable records fail closed with visible errors; "
                "the fail-closed compiler tests cover the rejection "
                "surface.",
    },
    "recursive_parent_value": {
        "status": "covered",
        "evidence": ("tests/test_native_value_links.py",
                     "tests/test_native_recursive_parent_value.py"),
        "modules": ("src/ct2trainer/native/compiler.py",
                    "src/ct2trainer/native/value_links.py",
                    "src/ct2trainer/native/engine.py"),
        "note": "moRecursiveSetValue value parents compile a deterministic "
                "write closure (deepest-first, ties ascending id, target "
                "last) into recursive_value.write_ids plan metadata via the "
                "shared value_links.recursive_write_closure; both plan "
                "validators re-derive and byte-verify the closure and refuse "
                "forged metadata. At set-value time the engine re-plans "
                "through the tested RecursiveSetValueModel, cross-checks the "
                "runtime plan against the compiled closure, and rewrites "
                "every descendant in one all-or-nothing transaction, "
                "updating frozen closure records so the freeze loop keeps "
                "the new bytes; bitfield/string closure members are refused "
                "fail-closed. Real in-game effect for the pinned corpus "
                "records remains an open AP-11 gate.",
    },
    "script_parent_activation": {
        "status": "covered",
        "evidence": ("tests/test_native_parent_activation.py",
                     "tests/test_native_staged_capability.py",
                     "tests/test_native_compiler.py"),
        "modules": ("src/ct2trainer/native/compiler.py",
                    "src/ct2trainer/native/engine.py",
                    "src/ct2trainer/native/parent_flags.py"),
        "note": "Script records with child-activation propagation options "
                "inherit the tested flag classes (both flags = "
                "required_dependency, moActivateChildrenAsWell only = "
                "direct_activation, moDeactivateChildrenAsWell only = "
                "collective_off; moBindActivation on a non-heading parent "
                "stays a visible named block). The engine activates the "
                "provider script first on ON and releases staged-child "
                "freezes before provider deactivation on OFF; "
                "parent_relations plan metadata is re-derived and "
                "tamper-refused by both plan validators. Value parents "
                "carrying the same flags stay inert (they compile as "
                "ordinary values).",
    },
    "signed_pointer_offset": {
        "status": "covered",
        "evidence": ("tests/test_native_compiler.py",),
        "modules": ("src/ct2trainer/native/compiler.py",),
        "note": "Pointer offset literals accept an explicit +/- sign with "
                "hex semantics preserved (+28 = 0x28, -0x10 = -16, "
                "+0x28 = 0x28); malformed forms ('++10', a bare sign, "
                "'0x', '10-', 'x1', whitespace) are rejected fail-closed. "
                "Signed offsets flow through value address chains and "
                "group-heading chains; corpus case-14 pins a heading-level "
                "signed chain (Offsets [0, +28]). Real in-game effect for "
                "the pinned corpus records remains an open AP-11 gate.",
    },
    "string_codepage": {
        "status": "covered",
        "evidence": ("tests/test_native_string_codec.py",
                     "tests/test_native_strings.py",
                     "tests/test_native_codepage_contract.py",
                     "tests/test_native_string_codepage_wiring.py"),
        "modules": ("src/ct2trainer/native/codepage_contract.py",
                    "src/ct2trainer/native/string_values.py",
                    "src/ct2trainer/native/string_runtime.py",
                    "src/ct2trainer/native/compiler.py"),
        "note": "The pinned CodePage contract (cp1250-1254/1257, UTF-8; 0 = "
                "ANSI default) is now wired through the string pipeline: an "
                "explicit non-default CodePage resolves to the pinned stdlib "
                "codec with unit size 1, survives value_types dispatch and "
                "plan validation, and round-trips through compile and the "
                "engine runtime with exact prefix/terminator semantics; "
                "CodePage 0 or an absent attribute keeps the legacy default "
                "codec so the 0.8 fixture pins stay byte-stable; unpinned "
                "values, Boolean flags, non-integer text and Unicode "
                "combinations are refused fail-closed with no writes. The "
                "pinned corpus carries 0 records with a foreign CodePage, "
                "so no denominator change.",
    },
    "table_lua_lifecycle": {
        "status": "covered",
        "evidence": ("tests/test_native_lua_bootstrap.py",
                     "tests/test_native_lua_activation.py",
                     "tests/test_native_compiler.py"),
        "modules": ("src/ct2trainer/native/lua_bootstrap.py",
                    "src/ct2trainer/native/lua_activation.py"),
        "note": "Table-level Lua is prepared statically without execution; "
                "activation receipts and phase boundaries are tested.",
    },
    "value_address_empty": {
        "status": "covered",
        "evidence": ("tests/test_native_addresses.py",
                     "tests/test_native_compiler.py"),
        "modules": ("src/ct2trainer/native/address_expression.py",
                    "src/ct2trainer/native/compiler.py"),
        "note": "Empty/null value addresses classify to navigation or are "
                "rejected fail-closed; addressless zero arrays navigate "
                "without an invented range (tested).",
    },
}


def sha256_file(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def load_json(path):
    if not os.path.isfile(path):
        raise FileNotFoundError("input artifact missing: %s" % path)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(out_dir, name, obj):
    path = os.path.join(out_dir, name)
    # newline="\n" keeps committed baselines byte-identical on every platform
    # (text-mode writes would translate to CRLF on Windows).
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")
    return path


def _refused(out_dir, protected_dirs):
    out = os.path.normpath(out_dir).lower()
    for d in protected_dirs:
        base = os.path.normpath(d).lower()
        if out == base or out.startswith(base + os.sep):
            return True
    return False


def pinned_gap_counts(gap_report):
    """Sum the per-table pinned gap_counts into one Counter."""
    counts = Counter()
    for table in gap_report["pinned_tables"]:
        for gap, n in table["counts"]["gap_counts"].items():
            counts[gap] += n
    return counts


def classify_missing_gates(missing_gates):
    """Split missing_gates into AP-11 game-gate exclusions and in-scope
    gate features, both in report order.

    An entry matching an AP-11 rule becomes an exclusion with its reason.
    Every remaining entry must match exactly one GATE_FEATURES contract;
    an unmatched entry is a contract error (exit 1), never silently
    dropped.
    """
    exclusions = []
    features = []
    for gate in missing_gates:
        reason = None
        for pattern, ap11_reason in AP11_GATE_RULES:
            if pattern in gate:
                reason = ap11_reason
                break
        if reason is not None:
            exclusions.append({"gate": gate, "reason": reason})
            continue
        contract = None
        for key, entry in GATE_FEATURES.items():
            if key in gate:
                contract = entry
                break
        if contract is None:
            raise ValueError("unhandled missing_gates entry: %r" % gate)
        features.append({"gate": gate, "status": contract["status"],
                         "evidence": list(contract["evidence"]),
                         "modules": list(contract["modules"]),
                         "note": contract["note"]})
    return exclusions, features


def build_feature_matrix(gap_report, exclusions, gate_features):
    """One matrix row per gap class (sorted) plus one per missing gate."""
    labels = gap_report["gap_labels"]
    counts = pinned_gap_counts(gap_report)
    matrix = {}
    for gap in sorted(labels):
        contract = FEATURES[gap]
        matrix[gap] = {
            "kind": "gap_class",
            "label": labels[gap]["label"],
            "requirement": labels[gap]["requirement"],
            "status": contract["status"],
            "evidence": list(contract["evidence"]),
            "modules": list(contract["modules"]),
            "note": contract["note"],
            "affected_records": counts.get(gap, 0),
            "ap11_excluded": False,
        }
    for index, feature in enumerate(gate_features, start=1):
        matrix["gate:%d" % index] = {
            "kind": "missing_gate",
            "gate": feature["gate"],
            "label": feature["gate"],
            "requirement": "AP-10 missing gate (in-scope)",
            "status": feature["status"],
            "evidence": feature["evidence"],
            "modules": feature["modules"],
            "note": feature["note"],
            "affected_records": None,
            "ap11_excluded": False,
        }
    for index, exclusion in enumerate(exclusions, start=1):
        matrix["ap11-gate:%d" % index] = {
            "kind": "missing_gate",
            "gate": exclusion["gate"],
            "label": exclusion["gate"],
            "requirement": "AP-11 game gate",
            "status": "missing",
            "evidence": [],
            "modules": [],
            "note": exclusion["reason"],
            "affected_records": None,
            "ap11_excluded": True,
        }
    return matrix


def compute_coverage(matrix):
    """Feature-weighted and action-weighted coverage over non-AP-11 rows.

    Action weighting is the sum of pinned affected_records per gap class
    (a record with several gaps counts once per class); AP-11 rows carry
    no action weight and are reported separately.
    """
    in_scope = {k: v for k, v in matrix.items() if not v["ap11_excluded"]}
    excluded = {k: v for k, v in matrix.items() if v["ap11_excluded"]}
    by_status = Counter(v["status"] for v in in_scope.values())
    feature_total = len(in_scope)
    feature_covered = by_status.get("covered", 0)
    total_weight = sum(v["affected_records"] or 0 for v in in_scope.values())
    covered_weight = sum(v["affected_records"] or 0 for v in in_scope.values()
                         if v["status"] == "covered")
    return {
        "features_total": len(matrix),
        "features_excluded_ap11": len(excluded),
        "features_in_scope": feature_total,
        "features_covered": feature_covered,
        "features_partial": by_status.get("partial", 0),
        "features_missing": by_status.get("missing", 0),
        "feature_weighted_coverage_percent":
            round(100.0 * feature_covered / feature_total, 2)
            if feature_total else 0.0,
        "actions_weight_total": total_weight,
        "actions_weight_ap11_excluded":
            sum(v["affected_records"] or 0 for v in excluded.values()),
        "actions_weight_in_scope": total_weight,
        "actions_weight_covered": covered_weight,
        "action_weighted_coverage_percent":
            round(100.0 * covered_weight / total_weight, 2)
            if total_weight else 0.0,
        "goal_percent": 90.0,
        "goal_reached": (
            feature_total > 0 and total_weight > 0
            and feature_covered / feature_total >= 0.90
            and covered_weight / total_weight >= 0.90),
    }


def build_top10(matrix, limit=10):
    """Still-open (partial/missing) non-AP-11 features, heaviest first."""
    open_rows = [(k, v) for k, v in matrix.items()
                 if not v["ap11_excluded"]
                 and v["status"] in ("partial", "missing")]
    open_rows.sort(key=lambda kv: (-(kv[1]["affected_records"] or 0), kv[0]))
    return [{"feature": k, "label": v["label"], "status": v["status"],
             "affected_records": v["affected_records"], "note": v["note"]}
            for k, v in open_rows[:limit]]


def build_consistency(gap_report, inventory, matrix, coverage, exclusions,
                      counts):
    """Cross-check the metric inputs against the committed artifacts.

    Every check is a (name, ok, expected, actual) record; ``all_ok`` is the
    conjunction. A failing check means the feature contract, the gap
    report or the inventory disagree and the run must not be consumed as
    evidence.
    """
    denom = gap_report["denominator"]
    tables = gap_report["pinned_tables"]
    labels = gap_report["gap_labels"]
    checks = []

    def add(name, expected, actual):
        checks.append({"check": name, "ok": expected == actual,
                       "expected": expected, "actual": actual})
        return expected == actual

    add("pinned_table_count", denom["unique_tables"], len(tables))
    add("expected_actions", denom["expected_actions"],
        sum(t["counts"]["expected_actions"] for t in tables))
    add("category_counts_sum",
        denom["expected_actions"] + denom["navigation_excluded"],
        sum(denom["category_counts"].values()))
    add("confirmed_game_effect_zero", 0,
        denom["confirmed_game_effect_actions"])
    top_gaps = gap_report["top_gaps_pinned"]
    add("top_gaps_pinned_match",
        [e["affected_records"] for e in top_gaps],
        [counts.get(e["gap"], 0) for e in top_gaps])
    pinned_gaps = set(counts)
    add("pinned_gaps_subset_of_labels", sorted(pinned_gaps),
        sorted(pinned_gaps & set(labels)))
    add("feature_contract_complete", sorted(labels), sorted(FEATURES))
    evidence = sorted({p for v in matrix.values() for p in v["evidence"]})
    add("evidence_files_exist", [],
        sorted(p for p in evidence
               if not os.path.exists(
                   os.path.join(REPO_ROOT, p.replace("/", os.sep)))))
    modules = sorted({p for v in matrix.values() for p in v["modules"]})
    add("module_paths_exist", [],
        sorted(p for p in modules
               if not os.path.exists(
                   os.path.join(REPO_ROOT, p.replace("/", os.sep)))))
    add("ap11_exclusions_present", True, len(exclusions) > 0)
    add("goal_90_percent_flag", "NOT REACHED", denom["goal_90_percent"])
    # The official goal metric is the feature-weighted coverage over the 39
    # in-scope features; goal_reached is the conjunction of feature- and
    # action-weighted metrics.
    add("coverage_goal_reached", True, coverage["goal_reached"])
    pinned_shas = {t["sha256"] for t in tables}
    inventory_shas = {t["sha256"] for t in inventory["tables"]}
    add("pinned_shas_in_inventory", sorted(pinned_shas),
        sorted(pinned_shas & inventory_shas))
    return {"all_ok": all(c["ok"] for c in checks), "checks": checks}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="feature_matrix",
        description="Deterministic feature matrix and coverage metric for "
                    "the 90% goal from the committed AP-10 gap report "
                    "(read-only, static, stdlib only).")
    parser.add_argument("--gap-report", default=DEFAULT_GAP_REPORT,
                        help="path to gap-report.json (default: "
                             "repo gap_inventory/gap-report.json)")
    parser.add_argument("--inventory", default=DEFAULT_INVENTORY,
                        help="path to inventory.json (default: "
                             "repo gap_inventory/inventory.json)")
    parser.add_argument("--output", default=None,
                        help="directory receiving feature-coverage.json "
                             "(required unless --list)")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID,
                        help="deterministic run identifier carried in the "
                             "'generated' and 'run_id' fields")
    parser.add_argument("--list", action="store_true",
                        help="print the static feature contract and exit")
    return parser.parse_args(argv)


def run(args):
    if args.list:
        for name in sorted(FEATURES):
            entry = FEATURES[name]
            print("%-28s %-8s %s" % (name, entry["status"],
                                     entry["note"][:72]))
        return 0
    if not args.output:
        print("an output directory is required unless --list is used")
        return 2
    try:
        gap_report = load_json(args.gap_report)
        inventory = load_json(args.inventory)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print("input error:", e)
        return 1
    missing = [k for k in REQUIRED_REPORT_KEYS if k not in gap_report]
    if missing:
        print("gap report missing keys:", missing)
        return 1
    missing = [k for k in REQUIRED_INVENTORY_KEYS if k not in inventory]
    if missing:
        print("inventory missing keys:", missing)
        return 1

    out_dir = os.path.abspath(args.output)
    protected = [os.path.dirname(os.path.abspath(args.gap_report)),
                 os.path.dirname(os.path.abspath(args.inventory))]
    if _refused(out_dir, protected):
        print("refusing to write into the directory containing the input "
              "artifacts:", args.output)
        return 3

    try:
        exclusions, gate_features = classify_missing_gates(
            gap_report["denominator"]["missing_gates"])
    except ValueError as e:
        print("contract error:", e)
        return 1

    counts = pinned_gap_counts(gap_report)
    matrix = build_feature_matrix(gap_report, exclusions, gate_features)
    coverage = compute_coverage(matrix)
    top10 = build_top10(matrix)
    consistency = build_consistency(gap_report, inventory, matrix,
                                    coverage, exclusions, counts)

    document = {
        "schema": SCHEMA_NAME,
        "generated": "run %s" % args.run_id,
        "run_id": args.run_id,
        "lane": "AP-10 feature matrix and coverage metric (read-only, static)",
        "source": {
            "gap_report": os.path.abspath(args.gap_report),
            "gap_report_sha256": sha256_file(args.gap_report),
            "inventory": os.path.abspath(args.inventory),
            "inventory_sha256": sha256_file(args.inventory),
        },
        "convention": {
            "denominator": "all 36 gap classes plus the non-AP-11 "
                           "missing_gates features; AP-11 game gates are "
                           "excluded and listed with reasons",
            "status_rules": {
                "covered": "dedicated existing tests/test_native_*.py "
                           "evidence exercises the feature (or its "
                           "fail-closed handling)",
                "partial": "native module exists but stage-1 model, "
                           "fail-closed blocked or incomplete coverage",
                "missing": "nothing exists in the native source",
            },
            "action_weighting": "sum of pinned affected_records per gap "
                                "class; records with several gaps count "
                                "once per class",
            "ap11_rule": "missing_gates entries matching real game "
                         "installs, observed game effect, VM/Clean-PC or "
                         "Steam Deck/Proton (incl. physical input) are "
                         "excluded from coverage",
        },
        "ap11_exclusions": exclusions,
        "coverage": coverage,
        "top10_priority": top10,
        "consistency": consistency,
        "feature_matrix": matrix,
    }

    os.makedirs(out_dir, exist_ok=True)
    out = _write_json(out_dir, "feature-coverage.json", document)
    print("wrote", out, os.path.getsize(out), "bytes")
    print("features:", coverage["features_in_scope"], "in scope",
          "(%d excluded AP-11)" % coverage["features_excluded_ap11"],
          "covered:", coverage["features_covered"])
    print("feature-weighted coverage: %.2f%%"
          % coverage["feature_weighted_coverage_percent"])
    print("action-weighted coverage: %.2f%% over %d weighted actions"
          % (coverage["action_weighted_coverage_percent"],
             coverage["actions_weight_in_scope"]))
    for row in [c for c in consistency["checks"] if not c["ok"]]:
        print("CONSISTENCY FAIL:", row["check"])
        print("  expected:", row["expected"])
        print("  actual:  ", row["actual"])
    print("consistency all_ok:", consistency["all_ok"])
    return 0 if consistency["all_ok"] else 2


def main(argv=None):
    return run(parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
