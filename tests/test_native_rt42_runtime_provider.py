"""RT-4.2 runtime provider model: R3 keep-first fallback, R4 mixed-dialect
Lua-registered providers, R7 bounded Windows API export registry.

Fixture process ``ct2rt42.exe`` mirrors the reference-table shapes:

- R3 (keep-first fallback): two providers register the same symbol; when
  the kept (document-order first) provider is blocked for an unrelated
  root, a dependent falls back to the first still-supported candidate in
  the keep-first scope; while the kept provider stays supported the plan
  stays byte-stable (the dependent binds to the kept provider).  Two
  boundary cases are pinned: a single-candidate symbol without an
  alternative keeps the classic generic refusal, and compatible
  shared-global duplicate sets keep the ambiguity refusal (the
  keep-first collapse never applies to compatible sets).
- R4 (mixed-dialect provider): DS2 record 87496 "[ Initialize ]" shape —
  the ENABLE Lua registers the base symbol and autoAssembles a proven
  literal body, the ``{$asm}`` [DISABLE] section releases it with the
  unquoted AA ``unregistersymbol`` form.  Release evidence is collected
  from ``kind == 'asm'`` parts only: the AA directive is the multi-name
  form (CE 7.5 autoassembler.pas:2492: the argument list is split on
  commas/whitespace, ``*`` = the program's own registered symbols),
  while the same spelling in a Lua part is the Lua API call that CE 7.5
  honors only with exactly one argument (LuaHandler.pas:5292: the symbol
  is deleted only when parameters:=lua_gettop(L) == 1), so unquoted names
  in Lua parts are not release evidence and the strict-pair regex stays
  the only Lua release evidence.
- R7 (API export registry): bare ``call GetAsyncKeyState`` /
  ``call FindWindowA`` targets with no record, table-Lua or user-symbol
  provider compile supported with the exact ``api_exports`` plan marker
  (bounded two-name registry, user32.dll) and resolve against the
  attached target's live PE export table at link time; a live registered
  symbol of the same name wins; an absent export fails closed with a
  named, actionable refusal before any target memory is touched; bare
  targets outside the registry (and in value address expressions) keep
  the classic generic refusal.

Engine level (fake memory, real Lua host):
- R4 roundtrip: the staged gate refuses the consumer before the provider
  activates; after activation the symbol is live at the registerSymbol
  address and the autoAssemble body is byte-exact; deactivation restores
  the body, releases the symbol exactly once, and the gate re-refuses.
- R7 engine: exactly one export resolution per activation of the
  alloc-based corpus shape, the call operand in the owned allocation
  targets the resolved export address byte-exactly, the bare name never
  pollutes the shared symbol map, an absent export refuses before any
  write, and disable deallocates the allocation without re-resolving.

Real in-game effect stays an open gate (AP-11).
"""
from contextlib import contextmanager
from copy import deepcopy
import re
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from test_native_compiler import script_record, value_record
from test_native_engine_code import Coordinator
from test_native_one_shot_lua_providers import CountingSymbols, OneShotMemory
from ct2trainer.native.compiler import (NativeCompileError, compile_table,
                                        validate_plan)
from ct2trainer.native.hooks import QuiescenceProof
from ct2trainer.native.engine import (NativeRuntimeError, TrainerEngine,
                                      validate_plan as validate_runtime_plan)
from ct2trainer.native.lua_program import lua_symbol_provides
from ct2trainer.native.memory import ProcessMemoryError

PROCESS = "ct2rt42.exe"


def write_table(directory: Path, body: str, name: str = "rt42.ct") -> Path:
    path = Path(directory) / name
    path.write_text('<CheatTable CheatEngineTableVersion="52"><CheatEntries>'
                    + body + '</CheatEntries></CheatTable>',
                    encoding="utf-8")
    return path


def by_id(plan: dict) -> dict:
    return {entry["id"]: entry for entry in plan["entries"]}


# ---------------------------------------------------------------------------
# R4 fixtures (DS2 87496 "[ Initialize ]" mixed-dialect provider shape)
# ---------------------------------------------------------------------------

# The embedded AA body is built as a quoted literal concatenation chain so
# that the [ENABLE]/[DISABLE] marker lines never appear as bare lines in
# the record source (the record parser would treat them as phase markers).
# The same chain is what _auto_assemble_proof proves statically and what
# the runtime autoAssemble publishes/restores.
R4_PROVIDER = (
    "[ENABLE]\n"
    "{$lua}\n"
    'rt42body = "[ENABLE]\\r\\n"\n'
    '  .. "ct2rt42.exe+40:\\r\\n"\n'
    '  .. "  db 01\\r\\n"\n'
    '  .. "[DISABLE]\\r\\n"\n'
    '  .. "ct2rt42.exe+40:\\r\\n"\n'
    '  .. "  db 00"\n'
    "registerSymbol('RtBase42', 0x1080, true)\n"
    "result, disableinfo = autoAssemble(rt42body)\n"
    "{$asm}\n"
    "[DISABLE]\n"
    "{$lua}\n"
    "result, disableinfo = autoAssemble(rt42body, false, disableinfo)\n"
    "{$asm}\n"
    "unregistersymbol(RtBase42)\n"
)

# Fail-closed boundary (the 17 "Static AA envelope" catalog rows): real AA
# enable content plus a Lua-registered symbol released by a foreign AA
# unregistersymbol in the static disable envelope.  The static cleanup gate
# fires, so the record stays blocked and the symbol is not a provider.
R4_BLOCKED = (
    "[ENABLE]\n"
    "{$lua}\n"
    "registerSymbol('RtReal42', 0x1080)\n"
    "{$asm}\n"
    "ct2rt42.exe+40:\n"
    "db 01\n"
    "[DISABLE]\n"
    "{$lua}\n"
    "unregisterSymbol('RtReal42')\n"
    "{$asm}\n"
    "ct2rt42.exe+40:\n"
    "db 00\n"
    "unregistersymbol(RtReal42)\n"
)

# ---------------------------------------------------------------------------
# R3 fixtures (keep-first duplicate provider pair)
# ---------------------------------------------------------------------------

# The kept (document-order first) provider of RtAlt42; its define alias
# references a symbol that no record registers, so the fixed-point pass
# blocks it after the provider map is built.
R3_KEPT_BLOCKED_SCRIPT = (
    "define(RtAlt42, RtMissing42+10)\n"
    "[ENABLE]\n"
    "registersymbol(RtAlt42)\n"
    "ct2rt42.exe+40:\n"
    "db 01\n"
    "[DISABLE]\n"
    "ct2rt42.exe+40:\n"
    "db 00\n"
    "unregistersymbol(RtAlt42)\n"
)

# Record 2 is the still-supported fallback candidate.  Record 3 consumes
# RtAlt42.
R3_KEPT_BLOCKED = (
    script_record(1, R3_KEPT_BLOCKED_SCRIPT,
                  "kept provider (blocked)")
    + script_record(2,
                    "define(RtAlt42, 0x50)\n"
                    "[ENABLE]\n"
                    "registersymbol(RtAlt42)\n"
                    "ct2rt42.exe+50:\n"
                    "db 01\n"
                    "[DISABLE]\n"
                    "ct2rt42.exe+50:\n"
                    "db 00\n"
                    "unregistersymbol(RtAlt42)\n",
                    "fallback provider")
    + value_record(3, "RtAlt42+4"))

# Same table with the kept provider self-contained: the byte-stable
# contract (dependency binds to the kept provider, the fallback stays
# unused while it is supported).
R3_KEPT_HEALTHY = (
    script_record(1,
                  "define(RtAlt42, 0x1000)\n"
                  "[ENABLE]\n"
                  "registersymbol(RtAlt42)\n"
                  "ct2rt42.exe+40:\n"
                  "db 01\n"
                  "[DISABLE]\n"
                  "ct2rt42.exe+40:\n"
                  "db 00\n"
                  "unregistersymbol(RtAlt42)\n",
                  "kept provider")
    + script_record(2,
                    "define(RtAlt42, 0x50)\n"
                    "[ENABLE]\n"
                    "registersymbol(RtAlt42)\n"
                    "ct2rt42.exe+50:\n"
                    "db 01\n"
                    "[DISABLE]\n"
                    "ct2rt42.exe+50:\n"
                    "db 00\n"
                    "unregistersymbol(RtAlt42)\n",
                    "shadowed provider")
    + value_record(3, "RtAlt42+4"))

# Identical shared-global declarers (the compatible duplicate branch,
# global_alloc.shared_provider_compatible short-circuit): both records
# stay supported and share the globalalloc pool, so the duplicate set is
# NOT collapsed keep-first — the dependent sees two supported providers
# and keeps the ambiguity refusal; the R3 scope fallback never applies
# to compatible sets.
R3_GLOBAL_DUPLICATES_SCRIPT = (
    "[ENABLE]\n"
    "label(RtDone42)\n"
    "globalalloc(RtGlb42, 4)\n"
    "RtGlb42:\n"
    "dd #100\n"
    "alloc(RtCave42, 1000)\n"
    "RtCave42:\n"
    "mov rcx, RtGlb42\n"
    "mov eax, [rcx]\n"
    "jmp RtDone42\n"
    "0x1000:\n"
    "jmp RtCave42\n"
    "RtDone42:\n"
    "[DISABLE]\n"
    "0x1000:\n"
    "db B8 01 00 00 00\n"
    "dealloc(RtCave42)\n"
    "dealloc(RtGlb42)\n"
)


# ---------------------------------------------------------------------------
# R7 fixtures (bare Windows API export call targets)
# ---------------------------------------------------------------------------

# Original 6 bytes at ct2rt42.exe+40 are six nops, exactly what the
# DISABLE section restores, so the publish-time disable-inverse check
# passes.  The 5-byte near call + 1 nop pad fills the 6-byte site.
R7_RECORD_1 = (
    "[ENABLE]\n"
    "ct2rt42.exe+40:\n"
    "  call GetAsyncKeyState\n"
    "  db 90\n"
    "[DISABLE]\n"
    "ct2rt42.exe+40:\n"
    "  db 90 90 90 90 90 90\n"
)
R7_RECORD_2 = (
    "[ENABLE]\n"
    "ct2rt42.exe+50:\n"
    "  call FindWindowA\n"
    "  db 90\n"
    "[DISABLE]\n"
    "ct2rt42.exe+50:\n"
    "  db 90 90 90 90 90 90\n"
)

# The corpus R7 shape (DS2 87792/87498/... thread records) places the
# bare API call inside an owned allocation body; the RT-5 G
# CreateThread/threadWait capability decision keeps those thread spawns
# blocked, so this is that shape minus the thread backend.  Allocation
# blocks skip the live entry-patch control-flow validation, so the
# call may target the resolved export.
R7_RECORD_ALLOC = (
    "[ENABLE]\n"
    "alloc(RtThread42, 16)\n"
    "registersymbol(RtThread42)\n"
    "RtThread42:\n"
    "  mov rcx, 6E\n"
    "  call GetAsyncKeyState\n"
    "  ret\n"
    "[DISABLE]\n"
    "unregistersymbol(RtThread42)\n"
    "dealloc(RtThread42)\n"
)


class RT42Memory(OneShotMemory):
    """OneShotMemory plus the cave allocation surface the R7 alloc-based
    roundtrip needs (same shape as the WP-51 cave fake) and a bounded
    live-export table for the R7 export resolution."""

    def __init__(self, exports=None, cave=0x10000, cave_size=0x1000):
        super().__init__()
        self.exports = dict(exports or {})
        self.export_requests = []
        self.cave, self.cave_size = cave, cave_size
        extended = bytearray(cave_size + cave - self.base)
        extended[:len(self.data)] = self.data
        self.data = extended
        self.allocations = {}
        self.allocation_protections = {}
        self.releases = []
        self._next = cave

    def module(self, name):
        if name.casefold() == PROCESS:
            return self.base, len(self.data)
        raise OSError("Unknown module")

    def allocate(self, size, near=None):
        base = self._next
        self._next += (size + 7) & ~7
        self.allocations[base] = size
        return base

    def allocation_size(self, address):
        return self.allocations[address]

    def protect_allocation(self, address, executable=True, writable=False):
        self.allocation_protections[address] = \
            (0x40 if writable else 0x20) if executable else 0x04

    def _query(self, address):
        for base, size in self.allocations.items():
            if base <= address < base + size:
                return SimpleNamespace(BaseAddress=base, AllocationBase=base,
                                       RegionSize=size, State=0x1000,
                                       Protect=self.allocation_protections
                                       .get(base, 0x04),
                                       Type=0x20000)
        if self.base <= address < self.base + len(self.data):
            # The module image region: committed PAGE_READWRITE evidence for
            # the linker's external-literal seal (hooks._rw_inventory
            # requires State 0x1000, Protect 0x04, a covering region and the
            # full _MEMORY_BASIC_INFORMATION field set incl. Type).
            return SimpleNamespace(BaseAddress=self.base,
                                   AllocationBase=self.base,
                                   RegionSize=len(self.data), State=0x1000,
                                   Protect=0x04, Type=0x10000)
        raise ValueError("unmapped allocation range")

    def release(self, address):
        self.releases.append(address)

    def resolve_export(self, module, export, *, pointer_size=None):
        self.export_requests.append((module, export))
        try:
            return self.exports[(module, export)]
        except KeyError:
            raise ProcessMemoryError(
                "no export named %s in module %s" % (export, module))


class DataCoordinator:
    """Held-data coordinator for the R4 external-literal child receipt.

    Mirrors the house convention (test_native_external_data): external
    literal data takes the held-data path (hold_data) and must never enter
    the instruction coordinator (hold_entries raises).
    """

    def __init__(self):
        self.holds = []

    @contextmanager
    def hold_data(self, memory, ranges):
        self.holds.append(tuple(ranges))
        yield QuiescenceProof(memory.identity, tuple(ranges),
                              'held-data-safe-point', lambda: True)

    def hold_entries(self, *args, **kwargs):
        raise AssertionError('External data must never enter the '
                             'instruction coordinator')


class RT42EngineBase(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def start_engine(self, memory, plan, coordinator=None):
        engine = TrainerEngine(plan, state_dir=self.root / "state",
                               process_lock_dir=self.root / "shared",
                               memory_factory=lambda name: memory,
                               hook_coordinator=coordinator
                               if coordinator is not None else Coordinator())
        engine.poll()
        self.assertTrue(engine.connected, engine.status)
        return engine


# ---------------------------------------------------------------------------
# R4: plan level
# ---------------------------------------------------------------------------

class R4PlanTests(RT42EngineBase):
    def test_mixed_dialect_provider_proves_symbol_and_stages_consumer(self):
        body = script_record(1, R4_PROVIDER, "Provider") \
            + value_record(2, "RtBase42+4")
        plan = compile_table(write_table(self.root, body), PROCESS)
        e = by_id(plan)
        self.assertEqual(plan["counts"]["total"], 2)
        self.assertEqual(plan["counts"]["blocked"], 0)
        # The provider: non-one-shot, static program refused (empty static
        # enable), rescued by the proven autoAssemble body; the symbol is
        # proven by the enable-Lua registration intersected with the
        # {$asm} unquoted release.
        self.assertTrue(e[1]["supported"], e[1]["reason"])
        self.assertFalse(e[1]["one_shot"])
        self.assertEqual(e[1]["provides"], ["RtBase42"])
        self.assertEqual(e[1]["requires"], [])
        self.assertEqual(e[1]["dependency_ids"], [])
        self.assertIsNone(e[1]["lua_program"]["static_program"])
        self.assertIsNotNone(e[1]["lua_program"]["auto_assemble"])
        self.assertNotIn("staged", e[1])
        self.assertNotIn("api_exports", e[1])
        # The consumer: supported, staged behind the provider.
        self.assertTrue(e[2]["supported"], e[2]["reason"])
        self.assertEqual(e[2]["requires"], ["RtBase42"])
        self.assertEqual(e[2]["dependency_ids"], [1])
        self.assertEqual(e[2]["staged"]["provider_ids"], [1])
        self.assertEqual(e[2]["staged"]["provider_labels"], [e[1]["path"]])
        self.assertEqual(plan["external_owned_providers"], {"rtbase42": 1})
        validate_plan(plan)
        validate_runtime_plan(plan)

    def test_release_in_a_lua_part_is_not_evidence(self):
        # The same unquoted spelling inside a {$lua} DISABLE part is the
        # Lua API call territory: without the quoted strict-pair form there
        # is no release evidence, so the record proves no symbol and the
        # consumer keeps the classic generic refusal.
        body = script_record(1,
                             "[ENABLE]\n"
                             "{$lua}\n"
                             "registerSymbol('RtLua42', 0x1080)\n"
                             "{$asm}\n"
                             "[DISABLE]\n"
                             "{$lua}\n"
                             "unregistersymbol(RtLua42)\n"
                             "{$asm}\n",
                             "lua-part release provider") \
            + value_record(2, "RtLua42+4")
        plan = compile_table(write_table(self.root, body), PROCESS)
        e = by_id(plan)
        self.assertTrue(e[1]["supported"], e[1]["reason"])
        self.assertEqual(e[1]["provides"], [])
        self.assertFalse(e[2]["supported"])
        self.assertEqual(e[2]["reason"],
                         "Required symbol has no unique supported provider: "
                         "RtLua42.")

    def test_real_aa_enable_with_foreign_release_stays_blocked(self):
        # The fail-closed boundary: the static envelope carries real enable
        # content, so the cleanup gate (not the no-content rescue) fires on
        # the foreign unregistersymbol; the record stays blocked with the
        # exact named reason and the symbol is not a provider.
        body = script_record(1, R4_BLOCKED, "blocked provider") \
            + value_record(2, "RtReal42+4")
        plan = compile_table(write_table(self.root, body), PROCESS)
        e = by_id(plan)
        self.assertFalse(e[1]["supported"])
        self.assertEqual(e[1]["reason"],
                         "Static AA envelope: Cleanup may only release "
                         "symbols/allocations owned by this program.")
        self.assertFalse(e[2]["supported"])
        self.assertEqual(e[2]["reason"],
                         "Required symbol has no unique supported provider: "
                         "RtReal42.")


class R4ExtractorTests(unittest.TestCase):
    """Pure-text extractor pins (no engine)."""

    def _source(self, enable_lua, disable_body):
        return ("[ENABLE]\n{$lua}\n" + enable_lua + "{$asm}\n"
                "[DISABLE]\n{$asm}\n" + disable_body + "\n")

    def test_aa_multi_name_release_proves_both_names(self):
        source = self._source(
            "registerSymbol('A42', 0x1000)\n"
            "registerSymbol('B42', 0x1004)\n",
            "unregistersymbol(A42, B42)")
        self.assertEqual(lua_symbol_provides(source), ["A42", "B42"])

    def test_aa_quoted_name_release_proves(self):
        source = self._source(
            "registerSymbol('A42', 0x1000)\n",
            'unregistersymbol("A42")')
        self.assertEqual(lua_symbol_provides(source), ["A42"])

    def test_aa_wildcard_release_proves_nothing(self):
        # '*' expands to the program's own registered symbols at runtime
        # (autoassembler.pas:2492); it carries no named static evidence.
        source = self._source(
            "registerSymbol('A42', 0x1000)\n",
            "unregistersymbol(*)")
        self.assertEqual(lua_symbol_provides(source), [])

    def test_aa_trailing_scalars_are_not_names(self):
        source = self._source(
            "registerSymbol('A42', 0x1000)\n",
            "unregistersymbol(A42, true, false, nil)")
        self.assertEqual(lua_symbol_provides(source), ["A42"])

    def test_unquoted_name_in_lua_part_is_not_release_evidence(self):
        # Lua dialect: the strict-pair (quoted) regex is the only release
        # evidence (LuaHandler.pas:5292 no-op semantics for the 2/3-arg
        # call); the unquoted AA spelling in a Lua part proves nothing.
        source = self._source(
            "registerSymbol('A42', 0x1000)\n",
            "unregistersymbol(A42)")
        # Force the disable body into the Lua dialect instead of AA.
        source = source.replace("[DISABLE]\n{$asm}\n", "[DISABLE]\n{$lua}\n")
        self.assertEqual(lua_symbol_provides(source), [])

    def test_max_providers_valve_keeps_extraction_empty(self):
        names = ["N%02d" % i for i in range(65)]  # 65 > MAX_PROVIDERS
        enable = "".join(
            "registerSymbol('%s', 0x%04x)\n" % (name, 0x1000 + i * 8)
            for i, name in enumerate(names))
        disable = "unregistersymbol(%s)\n" % ", ".join(names)
        self.assertEqual(lua_symbol_provides(self._source(enable, disable)),
                         [])


# ---------------------------------------------------------------------------
# R3: plan level
# ---------------------------------------------------------------------------

class R3PlanTests(RT42EngineBase):
    def test_blocked_keep_first_provider_falls_back_to_next_candidate(self):
        plan = compile_table(write_table(self.root, R3_KEPT_BLOCKED),
                             PROCESS)
        e = by_id(plan)
        self.assertFalse(e[1]["supported"])
        self.assertIn("RtMissing42", e[1]["reason"])
        self.assertIn("not registered anywhere", e[1]["reason"])
        # The shadowed duplicate stays supported (RT-4.1 dupIgnore
        # narrowing) and now serves the dependent through the keep-first
        # scope fallback.
        self.assertTrue(e[2]["supported"], e[2]["reason"])
        self.assertEqual(e[2]["provides"], ["RtAlt42"])
        self.assertTrue(e[3]["supported"], e[3]["reason"])
        self.assertEqual(e[3]["dependency_ids"], [2])
        self.assertEqual(e[3]["staged"]["provider_ids"], [2])
        # Two raw providers keep the symbol out of the handover map.
        self.assertNotIn("rtalt42", plan.get("external_owned_providers", {}))
        validate_plan(plan)
        validate_runtime_plan(plan)

    def test_kept_provider_supported_keeps_byte_stable_binding(self):
        plan = compile_table(write_table(self.root, R3_KEPT_HEALTHY),
                             PROCESS)
        e = by_id(plan)
        self.assertTrue(e[1]["supported"], e[1]["reason"])
        self.assertTrue(e[2]["supported"], e[2]["reason"])
        # The fallback stays unused: the dependent binds to the kept
        # (document-order first) provider.
        self.assertEqual(e[3]["dependency_ids"], [1])
        self.assertEqual(e[3]["staged"]["provider_ids"], [1])
        self.assertNotIn("rtalt42", plan.get("external_owned_providers", {}))
        validate_plan(plan)
        validate_runtime_plan(plan)

    def test_single_candidate_symbol_without_alternative_stays_blocked(self):
        # The kept provider is blocked and no alternative candidate exists:
        # the keep-first scope fallback has nothing to fall back to, so the
        # consumer keeps the classic generic refusal.  The symbol is still
        # registered in the table source (by the blocked provider), so the
        # actionable per-symbol report does not fire either.
        plan = compile_table(
            write_table(self.root,
                        script_record(1, R3_KEPT_BLOCKED_SCRIPT,
                                       "solo provider (blocked)")
                        + value_record(2, "RtAlt42+4")),
            PROCESS)
        e = by_id(plan)
        self.assertFalse(e[1]["supported"])
        self.assertIn("RtMissing42", e[1]["reason"])
        self.assertFalse(e[2]["supported"])
        self.assertEqual(
            e[2]["reason"],
            "Required symbol has no unique supported provider: RtAlt42.")
        validate_plan(plan)
        validate_runtime_plan(plan)

    def test_shared_global_compatible_duplicates_keep_ambiguity_refusal(self):
        # Identical shared-global declarers form a compatible duplicate set:
        # both stay supported and share the pool, and the set is NOT
        # collapsed keep-first, so the dependent sees two supported
        # providers and keeps the ambiguity refusal — the R3 scope fallback
        # only applies to non-compatible duplicate sets.
        body = (script_record(1, R3_GLOBAL_DUPLICATES_SCRIPT,
                              "Global provider A")
                + script_record(2, R3_GLOBAL_DUPLICATES_SCRIPT,
                                "Global provider B")
                + value_record(3, "RtGlb42+4"))
        plan = compile_table(write_table(self.root, body), PROCESS)
        e = by_id(plan)
        self.assertTrue(e[1]["supported"], e[1]["reason"])
        self.assertTrue(e[2]["supported"], e[2]["reason"])
        self.assertFalse(e[3]["supported"])
        self.assertEqual(
            e[3]["reason"],
            "Required symbol has no unique supported provider: RtGlb42.")
        validate_plan(plan)
        validate_runtime_plan(plan)


# ---------------------------------------------------------------------------
# R7: plan level
# ---------------------------------------------------------------------------

class R7PlanTests(RT42EngineBase):
    def test_bare_call_targets_get_the_bounded_markers(self):
        body = script_record(1, R7_RECORD_1, "AsyncCaller") \
            + script_record(2, R7_RECORD_2, "WindowCaller")
        plan = compile_table(write_table(self.root, body), PROCESS)
        e = by_id(plan)
        for entry_id, export in ((1, "GetAsyncKeyState"),
                                 (2, "FindWindowA")):
            with self.subTest(entry_id=entry_id):
                self.assertTrue(e[entry_id]["supported"],
                                e[entry_id]["reason"])
                self.assertEqual(e[entry_id]["api_exports"],
                                 {export: "user32.dll"})
                self.assertEqual(e[entry_id]["requires"], [export])
                self.assertEqual(e[entry_id]["dependency_ids"], [])
                self.assertNotIn("staged", e[entry_id])
        validate_plan(plan)
        validate_runtime_plan(plan)

    def test_value_expression_with_bare_api_name_stays_blocked(self):
        # The marker is a script-record feature: a value record whose
        # address expression names the bare API export keeps the classic
        # generic refusal and never gains a marker.
        body = script_record(1, R7_RECORD_1, "AsyncCaller") \
            + value_record(2, "GetAsyncKeyState+4")
        plan = compile_table(write_table(self.root, body), PROCESS)
        e = by_id(plan)
        self.assertTrue(e[1]["supported"], e[1]["reason"])
        self.assertFalse(e[2]["supported"])
        self.assertEqual(e[2]["reason"],
                         "Required symbol has no unique supported provider: "
                         "GetAsyncKeyState.")
        self.assertNotIn("api_exports", e[2])

    def test_blocked_entries_never_carry_markers(self):
        # The record both names a bare API target and requires a symbol
        # that no record registers: it is blocked, and the marker (which
        # may have been set for the earlier symbol in resolution order)
        # must not leak into the plan.
        body = script_record(1,
                             "[ENABLE]\n"
                             "ct2rt42.exe+60:\n"
                             "  mov eax, [RtMissing42]\n"
                             "  call GetAsyncKeyState\n"
                             "  db 90\n"
                             "[DISABLE]\n"
                             "ct2rt42.exe+60:\n"
                             "  db 90 90 90 90 90 90\n",
                             "mixed blocked")
        plan = compile_table(write_table(self.root, body), PROCESS)
        e = by_id(plan)
        self.assertFalse(e[1]["supported"])
        self.assertIn("RtMissing42", e[1]["reason"])
        self.assertNotIn("api_exports", e[1])


# ---------------------------------------------------------------------------
# R7: forged marker validation (both plan validators)
# ---------------------------------------------------------------------------

class R7ValidateTests(RT42EngineBase):
    def _valid_plan(self):
        body = script_record(1, R7_RECORD_1, "AsyncCaller")
        return compile_table(write_table(self.root, body), PROCESS)

    def test_forged_api_export_markers_refused_by_both_validators(self):
        base = self._valid_plan()
        cases = {
            "empty mapping":
                ({"GetAsyncKeyState": "user32.dll"}, {}),
            "over bound mapping":
                ({"GetAsyncKeyState": "user32.dll"},
                 {"GetAsyncKeyState": "user32.dll"}
                 | {"Export%02d" % i: "user32.dll" for i in range(32)}),
            "marker on blocked record":
                ({"GetAsyncKeyState": "user32.dll"},
                 {"GetAsyncKeyState": "user32.dll"},
                 [("kind", "blocked"), ("supported", False)]),
            "non-PE module basename":
                ({"GetAsyncKeyState": "user32.dll"},
                 {"GetAsyncKeyState": "user32"}),
            "non-string module value":
                ({"GetAsyncKeyState": "user32.dll"},
                 {"GetAsyncKeyState": 42}),
            "key not in requires":
                ({"GetAsyncKeyState": "user32.dll"},
                 {"FindWindowA": "user32.dll"}),
            "casefold-duplicate keys":
                ({"GetAsyncKeyState": "user32.dll"},
                 {"GetAsyncKeyState": "user32.dll",
                  "getasynckeystate": "user32.dll"}),
        }
        expected = {
            "empty mapping":
                "API export markers must be bounded nonempty mappings.",
            "over bound mapping":
                "API export markers must be bounded nonempty mappings.",
            "marker on blocked record":
                "API export markers require a supported script record.",
            "non-PE module basename":
                "API export modules must be PE basenames.",
            "non-string module value":
                "API export markers must map export names to module "
                "basenames.",
            "key not in requires":
                "API export markers must reference a record requirement.",
            "casefold-duplicate keys":
                "Duplicate API export marker.",
        }
        for name, payload in cases.items():
            plan = deepcopy(base)
            entry = plan["entries"][0]
            if len(payload) == 3:
                _original, forged, mutations = payload
            else:
                forged, mutations = payload[1], ()
            entry["api_exports"] = forged
            for key, value in mutations:
                entry[key] = value
            with self.subTest(case=name):
                with self.assertRaisesRegex(
                        NativeCompileError,
                        re.escape(expected[name])):
                    validate_plan(plan)
                with self.assertRaisesRegex(
                        NativeRuntimeError,
                        re.escape(expected[name])):
                    validate_runtime_plan(plan)


# ---------------------------------------------------------------------------
# R4: engine roundtrip
# ---------------------------------------------------------------------------

class R4EngineTests(RT42EngineBase):
    def test_provider_roundtrip_symbol_body_and_staged_gate(self):
        memory = RT42Memory()
        # Seed the consumer value at RtBase42+4 = 0x1084.
        memory.data[0x84:0x88] = struct.pack("<I", 0xAABBCCDD)
        body = script_record(1, R4_PROVIDER, "Provider") \
            + value_record(2, "RtBase42+4")
        plan = compile_table(write_table(self.root, body), PROCESS)
        # The proven autoAssemble body is a pure literal program, so the
        # child receipt is an external literal: its hook takes the held-data
        # coordinator path, not the instruction-coordinator one.
        engine = self.start_engine(memory, plan, DataCoordinator())
        engine.symbols = CountingSymbols(events=memory.events)
        # Staged gate: the consumer is pending while the provider is off.
        with self.assertRaisesRegex(
                NativeRuntimeError,
                "Staged record 'Value 2' requires active provider"):
            engine.read_value(2)
        # Activation: registerSymbol publishes the base, autoAssemble
        # publishes the body byte-exact.
        engine.toggle(1, True)
        self.assertIn(1, engine.applied)
        self.assertEqual(engine.symbols.get("rtbase42"), 0x1080)
        self.assertEqual(memory.data[0x40:0x41], b"\x01")
        # The staged consumer resolves byte-exact through the live symbol.
        self.assertEqual(engine.read_value(2), "2864434397")
        # Deactivation: the disable Lua retires the receipt (body restored
        # to the captured original) and scope retirement releases the
        # symbol exactly once; the gate re-refuses.
        engine.toggle(1, False)
        self.assertNotIn(1, engine.applied)
        self.assertEqual(memory.data[0x40:0x41], b"\x00")
        self.assertNotIn("rtbase42", engine.symbols)
        self.assertEqual(engine.symbols.removed, ["rtbase42"])
        with self.assertRaisesRegex(
                NativeRuntimeError,
                "Staged record 'Value 2' requires active provider"):
            engine.read_value(2)
        self.assertTrue(engine.close())


# ---------------------------------------------------------------------------
# R7: engine level
# ---------------------------------------------------------------------------

class R7EngineTests(RT42EngineBase):
    def _plan(self, record=R7_RECORD_1):
        return compile_table(
            write_table(self.root, script_record(1, record,
                                                 "AsyncCaller")),
            PROCESS)

    def _assert_alloc_call_targets(self, memory, manager, export_address):
        # The owned allocation body must carry exactly one near call
        # (mov rcx, 6E, call, ret) whose relative operand resolves
        # byte-exactly to the export address.  The mov's encoded size is
        # not pinned (nasm's imm8/imm32 choice); the call is located by
        # its unique 0xE8 opcode and must be immediately followed by ret.
        allocation = manager.allocations["rtthread42"]
        base = allocation["address"]
        self.assertEqual(base, 0x10000)
        raw = memory.read(base, allocation["actual_size"])
        call_sites = [index for index in range(len(raw) - 4)
                      if raw[index] == 0xE8]
        self.assertEqual(call_sites, [5])
        pos = call_sites[0]
        rel = int.from_bytes(raw[pos + 1:pos + 5], "little", signed=True)
        self.assertEqual(base + pos + 5 + rel, export_address)
        self.assertEqual(raw[pos + 5], 0xC3)

    def test_api_export_resolves_once_and_stays_out_of_symbol_map(self):
        memory = RT42Memory(exports={("user32.dll", "GetAsyncKeyState"):
                                      0x2000})
        engine = self.start_engine(memory, self._plan(R7_RECORD_ALLOC))
        engine.toggle(1, True)
        # Exactly one live export resolution, at link time.
        self.assertEqual(memory.export_requests,
                         [("user32.dll", "GetAsyncKeyState")])
        manager = engine.hooks[1]
        self._assert_alloc_call_targets(memory, manager, 0x2000)
        # The allocation's own symbol is registered; the bare API name
        # must not pollute the shared symbol map (the resolved address
        # lives only in the per-install overlay).
        self.assertEqual(engine.symbols.get("rtthread42"), 0x10000)
        self.assertNotIn("getasynckeystate", engine.symbols)
        # Deactivation unregisters the symbol and retains the allocation
        # (retention policy: no dealloc while the target is alive — the
        # same contract test_native_allocation_only_enable pins), without
        # re-resolving the export.
        engine.toggle(1, False)
        self.assertNotIn("rtthread42", engine.symbols)
        manager = engine.retired_hooks[0]
        self.assertEqual(manager.allocations["rtthread42"]["state"],
                         "retained")
        self.assertEqual(memory.releases, [])
        self.assertEqual(len(memory.export_requests), 1)
        self.assertTrue(engine.close())

    def test_absent_export_fails_closed_before_any_write(self):
        memory = RT42Memory()  # no exports
        memory.data[0x40:0x46] = b"\x90" * 6
        engine = self.start_engine(memory, self._plan())
        original = bytes(memory.data[0x40:0x46])
        with self.assertRaisesRegex(
                NativeRuntimeError,
                "Windows API export 'GetAsyncKeyState' \\(module user32"
                "\.dll\\) is not resolvable in the attached target "
                "process:.*no target memory was changed"):
            engine.toggle(1, True)
        self.assertEqual(memory.writes, [])
        self.assertEqual(bytes(memory.data[0x40:0x46]), original)
        self.assertNotIn(1, engine.applied)
        self.assertNotIn("getasynckeystate", engine.symbols)

    def test_live_registered_symbol_wins_without_resolve(self):
        memory = RT42Memory(exports={("user32.dll", "GetAsyncKeyState"):
                                      0x2000})
        engine = self.start_engine(memory, self._plan(R7_RECORD_ALLOC))
        # A live registration of the same name is the source of truth:
        # the export table is never consulted.
        engine.symbols["getasynckeystate"] = 0x3000
        engine.toggle(1, True)
        self.assertEqual(memory.export_requests, [])
        manager = engine.hooks[1]
        self._assert_alloc_call_targets(memory, manager, 0x3000)
        engine.toggle(1, False)
        self.assertEqual(len(memory.export_requests), 0)
        self.assertTrue(engine.close())


if __name__ == "__main__":
    unittest.main()
