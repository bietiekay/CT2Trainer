"""WP-46 part 2 (GC-E12): one-shot Lua provider handover + extended literal
registerSymbol extraction.

A one-shot record (missing or contentless [DISABLE]) registers its base
symbol from record Lua at activation and has no disable phase that could
release it.  WP-46 part 2 adopts that registration evidence statically so
the record becomes an external symbol provider:

Plan level (fixture mirrors the root-scratch case-28 shapes, module
ct2synth28.exe, P3Reload-style one-shot scan provider):
- one-shot ENABLE literal registration is adopted without a matching
  unregister (register ∩ unregister stays strict for non-one-shot);
- the CE helper form ``Register.symbol('name', ...)`` (case-insensitive
  dotted form) counts as registration evidence;
- ``unregisterSymbol('name', <one optional trailing argument>)`` counts as
  release evidence; a second trailing argument keeps the name unproven;
- keep-first duplicate policy unchanged: the later contested one-shot
  provider is blocked with the exact named reason and the contested symbol
  stays out of ``external_owned_providers``;
- non-one-shot register-only records stay unproven (fail-closed boundary);
- forged provides / tampered external_owned_providers are refused by BOTH
  plan validators;
- MAX_PROVIDERS=64 keeps the whole-extraction-empty behavior.

Engine level (fake memory, real Lua host):
- owner activates first (consumer toggle auto-enables the one-shot owner
  through the dependency machinery) and the consumer resolves byte-exact;
- one-shot OFF clears the saved wish but the effect and the owned symbol
  persist until scope retirement;
- the collision refusal stays byte-exact;
- release on detach: owner-scope retirement (trainer close or target exit)
  releases the one-shot-owned symbol exactly once, extending the WP-37
  exactly-once-release invariant to one-shot owners.

Real fixture-target proof stays an open gate (AP-11).
"""
from copy import deepcopy
import struct
import tempfile
import unittest
from pathlib import Path

from test_native_compiler import script_record, value_record
from test_native_engine import FakeMemory
from test_native_engine_code import Coordinator
from ct2trainer.native.compiler import (NativeCompileError, compile_table,
                                        validate_plan)
from ct2trainer.native.engine import (TrainerEngine, NativeRuntimeError,
                                      validate_plan as validate_runtime_plan)
from ct2trainer.native.lua_host import LuaHostError


PROCESS = "ct2synth28.exe"


# ---------------------------------------------------------------------------
# Plan-level fixtures (case-28 record shapes)
# ---------------------------------------------------------------------------

CASE28_BODY = (
    script_record(50,
                  "[ENABLE]\n"
                  "{$lua}\n"
                  "local scan = createMemScan()\n"
                  "scan:firstScan('48 8B 9F ?? ?? 00 00')\n"
                  "scan:waitTillDone()\n"
                  "registerSymbol('SynthBase28', scan.Result.getAddress(0))\n"
                  "{$asm}\n"
                  "[DISABLE]\n",
                  "one-shot scan provider")
    + value_record(51, "SynthBase28+4")
    + value_record(52, "[SynthBase28]+8")
    + script_record(53,
                     "[ENABLE]\n"
                     "{$lua}\n"
                     "Register.symbol('SynthHelper28', readQword('ct2synth28.exe+4100'))\n"
                     "{$asm}\n"
                     "[DISABLE]\n",
                     "helper-form one-shot provider")
    + value_record(54, "SynthHelper28+2")
    + script_record(55,
                     "[ENABLE]\n"
                     "{$lua}\n"
                     "registerSymbol('SynthContest28', 0x140007000)\n"
                     "{$asm}\n"
                     "[DISABLE]\n",
                     "contested provider A")
    + script_record(56,
                     "[ENABLE]\n"
                     "{$lua}\n"
                     "registerSymbol('SynthContest28', 0x140007100)\n"
                     "{$asm}\n"
                     "[DISABLE]\n",
                     "contested provider B")
    + value_record(57, "SynthContest28+4")
    + script_record(58,
                     "[ENABLE]\n"
                     "{$lua}\n"
                     "registerSymbol('SynthOnly28', 0x140007200)\n"
                     "{$asm}\n"
                     "alloc(synthOnlyCave28, 8)\n"
                     "[DISABLE]\n"
                     "dealloc(synthOnlyCave28)",
                     "register-only provider (non-one-shot)")
    + value_record(59, "SynthOnly28+4"))


def write_table(directory: Path, body: str, sections: str = "") -> Path:
    path = Path(directory) / "oneshot28.ct"
    path.write_text('<CheatTable CheatEngineTableVersion="52"><CheatEntries>'
                    + body + '</CheatEntries>' + sections + '</CheatTable>',
                    encoding="utf-8")
    return path


def compile_case28(root: Path) -> dict:
    return compile_table(write_table(root, CASE28_BODY), PROCESS)


def by_id(plan: dict) -> dict:
    return {entry["id"]: entry for entry in plan["entries"]}


class OneShotProviderPlanTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def test_case28_plan_matches_expected_state(self):
        plan = compile_case28(self.root)
        self.assertEqual(plan["counts"], {"total": 10, "supported": 8,
                                          "actionable": 8, "blocked": 2,
                                          "headings": 0})
        e = by_id(plan)
        # One-shot scan provider: registration adopted without unregister.
        self.assertTrue(e[50]["supported"], e[50]["reason"])
        self.assertTrue(e[50]["one_shot"])
        self.assertEqual(e[50]["provides"], ["SynthBase28"])
        self.assertEqual(e[50]["dependency_ids"], [])
        # Both consumers supported and staged on the owner.
        for consumer_id in (51, 52):
            entry = e[consumer_id]
            self.assertTrue(entry["supported"], entry["reason"])
            self.assertEqual(entry["requires"], ["SynthBase28"])
            self.assertEqual(entry["dependency_ids"], [50])
            self.assertEqual(entry["staged"]["provider_ids"], [50])
        self.assertEqual(plan["external_owned_providers"],
                         {"synthbase28": 50, "synthhelper28": 53})
        validate_plan(plan)
        validate_runtime_plan(plan)

    def test_helper_form_provider_adopts_dotted_case_insensitive(self):
        plan = compile_case28(self.root)
        e = by_id(plan)
        self.assertTrue(e[53]["supported"], e[53]["reason"])
        self.assertTrue(e[53]["one_shot"])
        self.assertEqual(e[53]["provides"], ["SynthHelper28"])
        self.assertTrue(e[54]["supported"], e[54]["reason"])
        self.assertEqual(e[54]["dependency_ids"], [53])
        # The lowercase dotted form is the same evidence.
        body = (script_record(1,
                              "[ENABLE]\n"
                              "{$lua}\n"
                              "register.symbol('SynthLow28', 0x140007300)\n"
                              "{$asm}\n"
                              "[DISABLE]\n",
                              "lowercase helper provider")
                + value_record(2, "SynthLow28+4"))
        low_plan = compile_table(write_table(self.root, body), PROCESS)
        self.assertEqual(by_id(low_plan)[1]["provides"], ["SynthLow28"])
        self.assertEqual(by_id(low_plan)[2]["dependency_ids"], [1])

    def test_contested_one_shot_providers_resolve_keep_first(self):
        plan = compile_case28(self.root)
        e = by_id(plan)
        self.assertTrue(e[55]["supported"], e[55]["reason"])
        self.assertFalse(e[56]["supported"])
        self.assertEqual(
            e[56]["reason"],
            "Symbol provider duplicate: synthcontest28 (kept provider 55); "
            "a later registration would shadow the kept one at runtime.")
        self.assertTrue(e[57]["supported"], e[57]["reason"])
        self.assertEqual(e[57]["dependency_ids"], [55])
        # Two raw providers keep the symbol out of the handover map.
        self.assertNotIn("synthcontest28",
                         plan.get("external_owned_providers", {}))

    def test_non_one_shot_register_only_stays_unproven(self):
        plan = compile_case28(self.root)
        e = by_id(plan)
        self.assertTrue(e[58]["supported"], e[58]["reason"])
        self.assertFalse(e[58]["one_shot"])
        self.assertEqual(e[58]["provides"], [])
        self.assertFalse(e[59]["supported"])
        self.assertEqual(e[59]["reason"],
                         "Required symbol has no unique supported provider: SynthOnly28.")

    def test_unregister_trailing_argument_adopts_strict_pair(self):
        body = (script_record(1,
                              "[ENABLE]\n"
                              "{$lua}\n"
                              "registerSymbol('SynthTail28', 0x140007400)\n"
                              "{$asm}\n"
                              "[DISABLE]\n"
                              "{$lua}\n"
                              "unregisterSymbol('SynthTail28', false)\n"
                              "{$asm}\n",
                              "trailing-arg provider")
                + value_record(2, "SynthTail28+4"))
        plan = compile_table(write_table(self.root, body), PROCESS)
        e = by_id(plan)
        self.assertTrue(e[1]["supported"], e[1]["reason"])
        self.assertFalse(e[1]["one_shot"])
        self.assertEqual(e[1]["provides"], ["SynthTail28"])
        self.assertEqual(e[2]["dependency_ids"], [1])
        self.assertEqual(plan["external_owned_providers"], {"synthtail28": 1})

    def test_unregister_two_trailing_arguments_stays_unproven(self):
        body = (script_record(1,
                              "[ENABLE]\n"
                              "{$lua}\n"
                              "registerSymbol('SynthBad28', 0x140007500)\n"
                              "{$asm}\n"
                              "[DISABLE]\n"
                              "{$lua}\n"
                              "unregisterSymbol('SynthBad28', false, extra)\n"
                              "{$asm}\n",
                              "over-arg provider")
                + value_record(2, "SynthBad28+4"))
        plan = compile_table(write_table(self.root, body), PROCESS)
        e = by_id(plan)
        self.assertEqual(e[1]["provides"], [])
        self.assertFalse(e[2]["supported"])
        self.assertEqual(e[2]["reason"],
                         "Required symbol has no unique supported provider: SynthBad28.")

    def test_over_bound_one_shot_registration_stays_unproven(self):
        # MAX_PROVIDERS = 64: the whole extraction stays empty, never
        # truncated.
        lines = "".join(
            f"registerSymbol('Sym{i:02d}', 0x14001{i:03X})\n"
            for i in range(65))
        body = (script_record(1,
                              "[ENABLE]\n{$lua}\n" + lines +
                              "{$asm}\n[DISABLE]\n",
                              "over-bound provider")
                + value_record(2, "Sym00+4"))
        plan = compile_table(write_table(self.root, body), PROCESS)
        e = by_id(plan)
        self.assertTrue(e[1]["supported"], e[1]["reason"])
        self.assertEqual(e[1]["provides"], [])
        self.assertFalse(e[2]["supported"])
        self.assertEqual(e[2]["reason"],
                         "Required symbol has no unique supported provider: Sym00.")

    def test_forged_provides_and_maps_refused_by_both_gates(self):
        plan = compile_case28(self.root)
        cases = (
            # Reassignment (a fresh list) keeps the nested lua_program
            # intact, so both gates trip on the entry/program provides
            # mismatch; an in-place mutation would also corrupt the nested
            # program (same list object) and trip its source re-derivation.
            ("forged extra provides on the one-shot owner",
             lambda p: p["entries"][0].__setitem__(
                 "provides", p["entries"][0]["provides"] + ["ForgedSym28"]),
             "Native Lua metadata does not match its source",
             "Native Lua metadata does not match its source"),
            ("forged emptied provides on the one-shot owner",
             lambda p: p["entries"][0].__setitem__("provides", []),
             "Native Lua metadata does not match its source",
             "Native Lua metadata does not match its source"),
            ("external map names an unknown provider",
             lambda p: p.__setitem__(
                 "external_owned_providers", {"synthbase28": 99}),
             "must reference known provider IDs",
             "must reference known provider IDs"),
            ("external map names a blocked value record",
             lambda p: p.__setitem__(
                 "external_owned_providers", {"synthbase28": 59}),
             "must name supported script records",
             "must name supported script records"),
            ("external map symbol not provided by the owner",
             lambda p: p.__setitem__(
                 "external_owned_providers", {"synthonly28": 50}),
             "must match the provider's symbols",
             "must match the provider's symbols"),
        )
        for name, forge, compile_message, runtime_message in cases:
            with self.subTest(name=name):
                forged = deepcopy(plan)
                forge(forged)
                with self.assertRaisesRegex(NativeCompileError, compile_message):
                    validate_plan(forged)
                with self.assertRaisesRegex(NativeRuntimeError, runtime_message):
                    validate_runtime_plan(forged)


# ---------------------------------------------------------------------------
# Engine-level fixtures
# ---------------------------------------------------------------------------

# Documented 14-argument firstScan form (the record-Lua scan profile); the
# plan-level fixture above keeps the P3Reload short form, which is pure
# text evidence at compile time.
SCAN_PROVIDER_LUA = (
    "[ENABLE]\n"
    "{$lua}\n"
    "local scan = createMemScan()\n"
    "scan.firstScan(soExactValue, vtByteArray, nil, \"48 8B 9F 90 E9\", nil,\n"
    "    getAddress(\"ct2synth28.exe\"), getAddress(\"ct2synth28.exe\") + getModuleSize(\"ct2synth28.exe\"),\n"
    "    \"+W-C\", fsmNotAligned, \"\", true, false, false, false)\n"
    "scan.waitTillDone()\n"
    "registerSymbol('SynthScan28', scan.Result)\n"
    "{$asm}\n"
    "[DISABLE]\n")

LITERAL_PROVIDER_LUA = (
    "[ENABLE]\n"
    "{$lua}\n"
    "registerSymbol('SynthOne28', 0x1080)\n"
    "{$asm}\n"
    "[DISABLE]\n")

# The AA dialect parses offset literals as hex by default (# selects
# decimal), so +0x14 is the decimal-20 patch site 0x1094 below 0x1080.
CONSUMER_PATCH = (
    "[ENABLE]\n"
    "assert(SynthScan28+0x14, 00 00 00 00)\n"
    "SynthScan28+0x14:\n"
    "db 01\n"
    "[DISABLE]\n"
    "assert(SynthScan28+0x14, 01 00 00 00)\n"
    "SynthScan28+0x14:\n"
    "db 00")


class OneShotMemory(FakeMemory):
    """FakeMemory with the identity/range/scan surface the engine Lua path
    requires plus a write event trace for the teardown-order proof."""

    def __init__(self):
        super().__init__()
        self.events = []

    @property
    def identity(self):
        return self.pid, self.creation_time

    def module(self, name):
        if name.casefold() == PROCESS:
            return self.base, len(self.data)
        raise OSError("Unknown module")

    def _range(self, address, size):
        if not self.base <= address or address + size > self.base + len(self.data):
            raise ValueError("outside owned fixture memory")

    def is_executable(self, address, size):
        return False

    def scan_matches(self, pattern, **options):
        hexs = pattern.replace("*", "?").replace(" ", "")
        raw = bytes.fromhex(hexs)
        wild = [char == "?" for char in hexs]
        start = options.get("start", self.base)
        end = options.get("end", self.base + len(self.data))
        matches = []
        for index in range(len(self.data) - len(raw) + 1):
            if not start <= self.base + index < end:
                continue
            chunk = self.data[index:index + len(raw)]
            if all(chunk[pos] == raw[pos] for pos in range(len(raw))
                   if not wild[pos]):
                matches.append(self.base + index)
        return matches

    def write(self, address, raw):
        self.events.append(("write", address))
        return super().write(address, raw)


class CountingSymbols(dict):
    """Symbol table that records every removal, for the exactly-once proof.

    With an ``events`` list attached, each removal is also appended to that
    list as ``("symbol-removed", key)`` so teardown order against memory
    writes is comparable in one timeline.  ``clear`` (the target-exit bulk
    release) records every removed key as well.
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

    def clear(self):
        for key in list(self.keys()):
            self._record(key)
        super().clear()


class OneShotHandoverEngineTests(unittest.TestCase):
    """One-shot owner handover on fake memory with a real Lua host."""

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

    def test_scan_provider_auto_enables_before_consumer_and_releases_once(self):
        memory = OneShotMemory()
        # Unique marker bytes at 0x1080 are the scan target; the consumer
        # patch site 0x1094 starts zero-filled.
        memory.data[0x80:0x85] = b"\x48\x8b\x9f\x90\xe9"
        body = (script_record(10, SCAN_PROVIDER_LUA, "one-shot scan provider")
                + script_record(20, CONSUMER_PATCH, "consumer patch"))
        plan = compile_table(write_table(self.root, body), PROCESS)
        self.assertEqual(plan["external_owned_providers"], {"synthscan28": 10})
        engine = self.start_engine(memory, plan)
        engine.symbols = CountingSymbols(events=memory.events)
        # The consumer toggle pulls in the one-shot owner first (dependency
        # auto-enable); the scan registers the symbol and the patch lands.
        engine.toggle(20, True)
        self.assertIn(10, engine.applied)
        self.assertIn(20, engine.applied)
        self.assertEqual(engine.symbols.get("synthscan28"), 0x1080)
        self.assertEqual(memory.read(0x1094, 4), b"\x01\x00\x00\x00")
        # Collision refusal stays byte-exact on the owned live symbol.
        host = engine.lua_activations[10].host
        with self.assertRaisesRegex(
                LuaHostError,
                "Symbol is already owned or the activation limit is reached"):
            host.execute('registerSymbol("SynthScan28", 0x10F0)')
        self.assertEqual(engine.symbols.get("synthscan28"), 0x1080)
        # Detach with the consumer still live: table teardown runs leaves
        # first, so the consumer patch is restored before the owner scope
        # releases its symbol — and exactly once.
        self.assertTrue(engine.close())
        self.assertEqual(memory.read(0x1094, 4), bytes(4))
        self.assertEqual(engine.symbols, {})
        self.assertEqual(engine.symbols.removed, ["synthscan28"])
        write_index = max(index for index, event in enumerate(memory.events)
                          if event == ("write", 0x1094))
        release_index = memory.events.index(("symbol-removed", "synthscan28"))
        self.assertLess(write_index, release_index)

    def test_literal_provider_value_consumers_and_one_shot_off_semantics(self):
        memory = OneShotMemory()
        # The provider base 0x1080 holds the 64-bit pointer qword 0x10C0;
        # the dereferenced consumer reads the float at 0x10C8.  The +0x20
        # consumer lives at 0x10A0, outside the pointer qword, so its seed
        # cannot corrupt the handover address.  (Address-expression
        # literals are hex by default, so +0x20 is the decimal offset 32.)
        memory.data[0x80:0x88] = struct.pack("<Q", 0x10C0)
        memory.data[0xA0:0xA4] = struct.pack("<I", 0x12345678)
        memory.data[0xC8:0xCC] = struct.pack("<f", 2.5)
        body = (script_record(10, LITERAL_PROVIDER_LUA, "one-shot provider")
                + value_record(20, "SynthOne28+0x20")
                + value_record(30, "[SynthOne28]+8", value_type="Float"))
        plan = compile_table(write_table(self.root, body), PROCESS)
        validate_plan(plan)
        validate_runtime_plan(plan)
        engine = self.start_engine(memory, plan)
        engine.symbols = CountingSymbols()
        # Staged consumers stay pending while the provider is not live.
        with self.assertRaisesRegex(
                NativeRuntimeError, "requires active provider"):
            engine.read_value(20)
        engine.toggle(10, True)
        self.assertEqual(engine.symbols.get("synthone28"), 0x1080)
        self.assertEqual(engine.read_value(20), "305419896")
        self.assertEqual(engine.read_value(30), "2.5")
        # One-shot OFF: zero backend operations, wish cleared, effect and
        # the owned symbol persist until scope retirement.
        engine.toggle(10, False)
        self.assertTrue(engine.one_shot.query(10)["effect_persists"])
        self.assertIn(10, engine.applied)
        self.assertIn("synthone28", engine.symbols)
        self.assertEqual(engine.read_value(20), "305419896")
        # Scope retirement at trainer close releases exactly once.
        self.assertTrue(engine.close())
        self.assertEqual(engine.symbols, {})
        self.assertEqual(engine.symbols.removed, ["synthone28"])

    def test_target_exit_releases_one_shot_symbol_exactly_once(self):
        memory = OneShotMemory()
        body = (script_record(10, LITERAL_PROVIDER_LUA, "one-shot provider")
                + value_record(20, "SynthOne28+4"))
        plan = compile_table(write_table(self.root, body), PROCESS)
        engine = self.start_engine(memory, plan)
        engine.symbols = CountingSymbols()
        engine.toggle(10, True)
        self.assertIn("synthone28", engine.symbols)
        memory.alive = False
        engine.poll()
        # The confirmed target exit retires the owner scope and clears the
        # engine symbol table: the one-shot symbol is released exactly once.
        self.assertNotIn("synthone28", engine.symbols)
        self.assertEqual(engine.symbols.removed, ["synthone28"])
        self.assertEqual(engine.lua_activations, {})
        self.assertIn("Target ended", engine.status)


if __name__ == "__main__":
    unittest.main()
