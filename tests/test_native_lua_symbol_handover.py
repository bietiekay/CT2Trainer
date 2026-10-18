"""WP-37: Lua-owned symbol handover contract (reference plan §10, case-24).

A record can own symbols through two handover mechanisms: (a) embedded
record Lua that statically proves a registerSymbol/unregisterSymbol pair,
and (b) an allocation-only program (WP-29 profile) that registers its
allocation.  Consumers may require such symbols without registering them
themselves; the owning record becomes their activation dependency and
releases each symbol exactly once on its own deactivation.

Covered plan-level: the ``external_owned_providers`` map construction,
consumer dependency wiring, keep-first duplicate-provider resolution with
the named reason, foreign-release refusals surfaced by the wave-B1
re-derivation, the wildcard-cleanup combination guard (wave B2), table-Lua
exclusion, and forged-map rejection by both ``validate_plan`` gates.

Covered engine-level with a fake-memory/coordinator scaffold: the
dependent/consumer guards that keep the owning record's Lua DISABLE phase
from running while a consumer is live, the exactly-once symbol release on
clean deactivation, and the leaves-first detach order with an event trace
proving the consumer AA tears down before the owner releases its symbol.
The engine fixture uses the pure-Lua provider shape because the engine
cannot enable allocation-only static programs (see the open gates); the
allocation-only mechanism is proven plan-level.  Real fixture-target
proof is deferred to the open gates.
"""
from copy import deepcopy
import tempfile
import unittest
import xml.sax.saxutils
from pathlib import Path

from test_native_compiler import script_record, value_record
from test_native_engine import FakeMemory
from test_native_engine_code import Coordinator
from ct2trainer.native.compiler import (NativeCompileError, compile_table,
                                        validate_plan)
from ct2trainer.native.engine import (TrainerEngine, NativeRuntimeError,
                                      validate_plan as validate_runtime_plan)
from ct2trainer.native.lua_host import LuaHostError


HANDOVER_PROVIDER = (
    "[ENABLE]\n"
    "{$lua}\n"
    "registerSymbol('HandoverBase', 0x1040)\n"
    "{$asm}\n"
    "alloc(ProviderData,16)\n"
    "registersymbol(ProviderData)\n"
    "[DISABLE]\n"
    "{$lua}\n"
    "unregisterSymbol('HandoverBase')\n"
    "{$asm}\n"
    "unregistersymbol(ProviderData)\n"
    "dealloc(ProviderData)")


def lua_provider(sym: str) -> str:
    return ("[ENABLE]\n"
            "{$lua}\n"
            f"registerSymbol('{sym}', 0x1040)\n"
            "{$asm}\n"
            "[DISABLE]\n"
            "{$lua}\n"
            f"unregisterSymbol('{sym}')\n"
            "{$asm}")


CONSUMER_PATCH = (
    "[ENABLE]\n"
    "assert(HandoverBase+10, 00 00 00 00)\n"
    "HandoverBase+10:\n"
    "db 01\n"
    "[DISABLE]\n"
    "assert(HandoverBase+10, 01 00 00 00)\n"
    "HandoverBase+10:\n"
    "db 00")


def write_table(directory: Path, body: str, sections: str = "") -> Path:
    path = Path(directory) / "handover.ct"
    path.write_text('<CheatTable CheatEngineTableVersion="52"><CheatEntries>'
                    + body + '</CheatEntries>' + sections + '</CheatTable>',
                    encoding="utf-8")
    return path


def compile_table_in(directory: Path, body: str, process: str = "Target.exe",
                     sections: str = "") -> dict:
    return compile_table(write_table(directory, body, sections), process)


class ExternalOwnedPlanTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def test_mixed_provider_publishes_map_and_consumer_dependencies(self):
        plan = compile_table_in(
            self.root,
            script_record(10, HANDOVER_PROVIDER, "handover provider")
            + value_record(20, "HandoverBase+10")
            + value_record(30, "ProviderData+8"))
        self.assertEqual(plan["counts"]["blocked"], 0)
        provider = plan["entries"][0]
        self.assertTrue(provider["supported"], provider["reason"])
        self.assertEqual(provider["provides"], ["HandoverBase", "ProviderData"])
        self.assertIn("lua_program", provider)
        self.assertTrue(provider["lua_program"]["static_program"]["allocation_only"])
        for entry in plan["entries"][1:]:
            self.assertTrue(entry["supported"], entry["reason"])
            self.assertEqual(entry["dependency_ids"], [10])
            self.assertEqual(entry["staged"]["provider_ids"], [10])
        # Both handover mechanisms publish the same owning record.
        self.assertEqual(plan["external_owned_providers"],
                         {"handoverbase": 10, "providerdata": 10})
        validate_plan(plan)
        validate_runtime_plan(plan)

    def test_duplicate_lua_providers_resolve_keep_first(self):
        source = lua_provider("HandoverSym")
        plan = compile_table_in(self.root, script_record(0, source)
                                + script_record(1, source)
                                + value_record(2, "HandoverSym+4"))
        self.assertEqual(plan["counts"]["blocked"], 1)
        self.assertTrue(plan["entries"][0]["supported"])
        self.assertEqual(plan["entries"][1]["reason"],
                         "Symbol provider duplicate: handoversym (kept provider 0); "
                         "a later registration would shadow the kept one at runtime.")
        self.assertTrue(plan["entries"][2]["supported"], plan["entries"][2]["reason"])
        self.assertEqual(plan["entries"][2]["dependency_ids"], [0])
        # Two raw providers make the symbol contested: it stays out of the
        # map and keeps the ordinary keep-first provider rule.
        self.assertNotIn("external_owned_providers", plan)

    def test_foreign_unregister_surfaces_named_handover_reason(self):
        consumer = (
            "[ENABLE]\n"
            "assert(HandoverSym+10, 00 00 00 00)\n"
            "HandoverSym+10:\n"
            "db 01\n"
            "[DISABLE]\n"
            "assert(HandoverSym+10, 01 00 00 00)\n"
            "HandoverSym+10:\n"
            "db 00\n"
            "unregistersymbol(HandoverSym)")
        plan = compile_table_in(
            self.root,
            script_record(0, lua_provider("HandoverSym"))
            + script_record(1, consumer)
            + value_record(2, "HandoverSym+4"))
        self.assertTrue(plan["entries"][0]["supported"])
        self.assertFalse(plan["entries"][1]["supported"])
        # Wave B1 re-derives both halves of the compound wave-A reason with
        # the external-ownership context; the data-dialect half raises the
        # named handover refusal, so it surfaces in both halves.
        self.assertEqual(plan["entries"][1]["reason"],
                         "Program may not unregister or deallocate the "
                         "externally owned symbol HandoverSym. "
                         "Native assembly: Program may not unregister or "
                         "deallocate the externally owned symbol HandoverSym.")
        self.assertTrue(plan["entries"][2]["supported"], plan["entries"][2]["reason"])
        self.assertEqual(plan["entries"][2]["dependency_ids"], [0])
        self.assertEqual(plan["external_owned_providers"], {"handoversym": 0})

    def test_foreign_dealloc_surfaces_named_handover_reason(self):
        consumer = ("[ENABLE]\n"
                    "alloc(OwnedAlloc,16)\n"
                    "registersymbol(OwnedAlloc)\n"
                    "[DISABLE]\n"
                    "unregistersymbol(OwnedAlloc)\n"
                    "dealloc(HandoverSym)")
        plan = compile_table_in(self.root,
                                script_record(0, lua_provider("HandoverSym"))
                                + script_record(1, consumer))
        self.assertTrue(plan["entries"][0]["supported"])
        self.assertFalse(plan["entries"][1]["supported"])
        self.assertEqual(plan["entries"][1]["reason"],
                         "Unsupported AA directive: alloc. Native assembly: "
                         "Program may not unregister or deallocate the "
                         "externally owned symbol HandoverSym.")
        self.assertEqual(plan["external_owned_providers"], {"handoversym": 0})

    def test_wildcard_cleanup_with_external_require_is_blocked(self):
        consumer = ("[ENABLE]\n"
                    "alloc(OwnedData,16)\n"
                    "registersymbol(OwnedData)\n"
                    "assert(HandoverSym, 00 00 00 00)\n"
                    "[DISABLE]\n"
                    "unregistersymbol(*)\n"
                    "dealloc(*)")
        plan = compile_table_in(self.root,
                                script_record(0, lua_provider("HandoverSym"))
                                + script_record(1, consumer))
        self.assertTrue(plan["entries"][0]["supported"])
        self.assertFalse(plan["entries"][1]["supported"])
        self.assertEqual(plan["entries"][1]["reason"],
                         "Program cannot combine wildcard cleanup with "
                         "externally owned symbol HandoverSym.")
        self.assertEqual(plan["external_owned_providers"], {"handoversym": 0})

    def test_wildcard_cleanup_without_external_require_stays_supported(self):
        consumer = ("[ENABLE]\n"
                    "alloc(OwnedData2,16)\n"
                    "registersymbol(OwnedData2)\n"
                    "[DISABLE]\n"
                    "unregistersymbol(*)\n"
                    "dealloc(*)")
        plan = compile_table_in(self.root,
                                script_record(0, lua_provider("HandoverSym"))
                                + script_record(1, consumer))
        self.assertTrue(plan["entries"][1]["supported"], plan["entries"][1]["reason"])
        self.assertEqual(plan["external_owned_providers"],
                         {"handoversym": 0, "owneddata2": 1})

    def test_table_lua_claimed_symbol_stays_out_of_map(self):
        # Only the {$lua}-section shape parses into lua parts; a plain
        # [ENABLE]/[DISABLE]-only table Lua (corpus case-10 shape) is asm
        # text, proves no symbol pair and cannot claim the exclusion.
        sections = ("<LuaScript>{$lua}\n"
                    "[ENABLE]\n"
                    "registerSymbol('SharedSym', 0x2000)\n"
                    "[DISABLE]\n"
                    "unregisterSymbol('SharedSym')\n"
                    "{$asm}</LuaScript>")
        plan = compile_table_in(
            self.root,
            script_record(10, lua_provider("SharedSym"))
            + value_record(20, "SharedSym+4"),
            sections=sections)
        self.assertTrue(plan["entries"][0]["supported"], plan["entries"][0]["reason"])
        self.assertTrue(plan["entries"][1]["supported"], plan["entries"][1]["reason"])
        # The table Lua has no owning record to name as releaser, so the
        # claimed symbol stays out of the map; the record provider still
        # serves ordinary consumer dependencies.
        self.assertEqual(plan["entries"][1]["dependency_ids"], [10])
        self.assertNotIn("external_owned_providers", plan)

    def test_allocation_only_provider_is_in_map(self):
        provider = ("[ENABLE]\n"
                    "alloc(SynthBase,8)\n"
                    "registersymbol(SynthBase)\n"
                    "[DISABLE]\n"
                    "unregistersymbol(SynthBase)\n"
                    "dealloc(SynthBase)")
        plan = compile_table_in(self.root,
                                script_record(10, provider)
                                + value_record(20, "SynthBase+4"))
        self.assertTrue(plan["entries"][0]["supported"], plan["entries"][0]["reason"])
        self.assertTrue(plan["entries"][0]["program"]["allocation_only"])
        self.assertTrue(plan["entries"][1]["supported"], plan["entries"][1]["reason"])
        self.assertEqual(plan["entries"][1]["dependency_ids"], [10])
        self.assertEqual(plan["external_owned_providers"], {"synthbase": 10})
        validate_plan(plan)
        validate_runtime_plan(plan)


class ExternalOwnedGateTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.base_plan = compile_table_in(
            self.root,
            script_record(10, HANDOVER_PROVIDER, "handover provider")
            + value_record(20, "HandoverBase+10")
            + value_record(30, "ProviderData+8"))
        self.blocked_plan = compile_table_in(
            self.root,
            script_record(0, lua_provider("HandoverSym"))
            + script_record(1,
                            "[ENABLE]\n"
                            "assert(HandoverSym+10, 00 00 00 00)\n"
                            "HandoverSym+10:\n"
                            "db 01\n"
                            "[DISABLE]\n"
                            "assert(HandoverSym+10, 01 00 00 00)\n"
                            "HandoverSym+10:\n"
                            "db 00\n"
                            "unregistersymbol(HandoverSym)"))
        self.assertEqual(self.blocked_plan["external_owned_providers"],
                         {"handoversym": 0})
        self.assertFalse(self.blocked_plan["entries"][1]["supported"])

    def test_forged_maps_are_refused_by_both_gates(self):
        cases = (
            ("non-dict map", self.base_plan, ["handoverbase"],
             "must be a symbol-to-provider map"),
            ("non-string key", self.base_plan, {10: 10},
             "keys must be symbol names"),
            ("unknown provider id", self.base_plan, {"handoverbase": 99},
             "must reference known provider IDs"),
            ("non-int provider id", self.base_plan, {"handoverbase": "10"},
             "must reference known provider IDs"),
            ("blocked provider record", self.blocked_plan, {"handoversym": 1},
             "must name supported script records"),
            ("symbol not provided by owner", self.base_plan,
             {"unknownsym": 10},
             "must match the provider's symbols"),
        )
        for name, base, forged, message in cases:
            with self.subTest(name=name):
                plan = deepcopy(base)
                plan["external_owned_providers"] = forged
                with self.assertRaisesRegex(NativeCompileError, message):
                    validate_plan(plan)
                with self.assertRaisesRegex(NativeRuntimeError, message):
                    validate_runtime_plan(plan)


class HandoverMemory(FakeMemory):
    """FakeMemory extended with the identity/range surface the engine Lua
    path requires plus a write event trace for the teardown-order proof."""

    def __init__(self):
        super().__init__()
        self.events = []

    @property
    def identity(self):
        return self.pid, self.creation_time

    def _range(self, address, size):
        if not self.base <= address or address + size > self.base + len(self.data):
            raise ValueError("outside owned fixture memory")

    def is_executable(self, address, size):
        return False

    def write(self, address, raw):
        self.events.append(("write", address))
        return super().write(address, raw)


class CountingSymbols(dict):
    """Symbol table that records every removal, for the exactly-once proof.

    With an ``events`` list attached, each removal is also appended to that
    list as ``("symbol-removed", key)`` so teardown order against memory
    writes is comparable in one timeline.
    """

    def __init__(self, events=None):
        super().__init__()
        self.removed = []
        self.events = events

    def _record(self, key):
        self.removed.append(key)
        if self.events is not None:
            self.events.append(("symbol-removed", key))

    def __delitem__(self, key):
        super().__delitem__(key)
        self._record(key)

    def pop(self, key, *default):
        try:
            value = super().pop(key)
        except KeyError:
            if default:
                return default[0]
            raise
        self._record(key)
        return value


class HandoverEngineTests(unittest.TestCase):
    """Teardown-order invariants on fake memory with a real Lua host."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def start_engine(self, memory, plan):
        engine = TrainerEngine(plan, state_dir=self.root / "state",
                               process_lock_dir=self.root / "shared",
                               memory_factory=lambda name: memory,
                               hook_coordinator=Coordinator())
        engine.poll()
        self.assertTrue(engine.connected, engine.status)
        return engine

    def handover_plan(self, process="FixtureTarget.exe"):
        # The engine fixture uses the pure-Lua provider shape: the engine
        # cannot enable allocation-only static programs (HookManager.stage
        # needs nonempty linked blocks, link_program yields none), so the
        # handover proof rides on the Lua registration only.  The
        # allocation-only mechanism is proven plan-level.
        body = (script_record(10, lua_provider("HandoverBase"),
                              "handover provider")
                + script_record(20, CONSUMER_PATCH, "consumer"))
        plan = compile_table(write_table(self.root, body), process)
        self.assertEqual(plan["external_owned_providers"],
                         {"handoverbase": 10})
        return plan

    def test_clean_disable_releases_each_symbol_exactly_once(self):
        memory = HandoverMemory()
        engine = self.start_engine(memory, self.handover_plan())
        engine.symbols = CountingSymbols()
        # HandoverBase+10 is 0x1050 (hex offsets).
        engine.toggle(10, True)
        self.assertEqual(engine.symbols.get("handoverbase"), 0x1040)
        engine.toggle(20, True)
        self.assertEqual(memory.read(0x1050, 4), b"\x01\x00\x00\x00")
        # The owner cannot deactivate while a consumer is live: its Lua
        # DISABLE phase must not run before the consumer AA tears down.
        with self.assertRaisesRegex(NativeRuntimeError,
                                    "Disable dependent entries first"):
            engine.toggle(10, False)
        self.assertIn(10, engine.applied)
        self.assertIn("handoverbase", engine.symbols)
        # The Lua host applies the same guard to an explicit unregister.
        host = engine.lua_activations[10].host
        with self.assertRaisesRegex(
                LuaHostError,
                "Disable symbol consumers before unregistering their provider"):
            host.execute('unregisterSymbol("HandoverBase")')
        self.assertIn("handoverbase", engine.symbols)
        # Consumer off cleanly, then the owner: the DISABLE Lua releases
        # HandoverBase and nothing else is owned by the record.
        engine.toggle(20, False)
        self.assertEqual(memory.read(0x1050, 4), bytes(4))
        engine.toggle(10, False)
        self.assertNotIn("handoverbase", engine.symbols)
        self.assertEqual(engine.symbols.removed, ["handoverbase"])
        self.assertTrue(engine.close())

    def test_detach_tears_down_consumer_before_owner_releases_symbols(self):
        memory = HandoverMemory()
        engine = self.start_engine(memory, self.handover_plan())
        engine.symbols = CountingSymbols(events=memory.events)
        engine.toggle(10, True)
        engine.toggle(20, True)
        self.assertEqual(memory.read(0x1050, 4), b"\x01\x00\x00\x00")
        # Detach with the consumer still live: table teardown runs after
        # the record teardowns, leaves first, so the consumer patch is
        # restored before the owner's Lua scope releases its symbol.
        self.assertTrue(engine.close())
        self.assertEqual(memory.read(0x1050, 4), bytes(4))
        self.assertEqual(engine.symbols, {})
        self.assertEqual(engine.symbols.removed, ["handoverbase"])
        write_index = max(index for index, event in enumerate(memory.events)
                          if event == ("write", 0x1050))
        release_index = memory.events.index(("symbol-removed", "handoverbase"))
        self.assertLess(write_index, release_index)


if __name__ == "__main__":
    unittest.main()
