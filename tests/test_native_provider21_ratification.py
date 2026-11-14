"""Provider-21 by-design ratification (tests only, 0.50 cycle).

The 17 "no unique supported provider" rows of the post-0.49 catalog
census that stay blocked by design: each is a dependent row whose
provider record is itself blocked by a documented named condition.
This file pins, with self-contained synthetic fixtures mirroring the
real-table shapes (no TableReferences, no CE inputs, no real-table path
references — the real-table probing evidence lives in side/evidence/),
for every cluster:

1. the provider's exact block reason,
2. the dependent rows' exact generic refusal,
3. the counter-proof that the dependent rows resolve once the
   documented provider condition is met — no hidden second gate.

Clusters (real rows in parentheses):

- Cronos pBase (3 rows: 1337270007 / 1337264117 / 1337264120, symbol
  ``gun``, provider 1337261940): the provider releases the externally
  owned symbol pBase on disable (owned by record 1337263367) — the WP-37
  named handover refusal; the documented "1 pBase Cronos" residual.
- Cyberpunk2077 healthPtr (4 rows: 273 / 274 / 275 / 594, provider 259
  "Health Pointer"): a table typo — ``aobscanmodule(health1,$proces,...)``
  next to a correctly spelled ``aobscanmodule(health2,$process,...)`` in
  the same program — is the named "Quoted atom '$proces' must be a module
  basename (.exe/.dll)." refusal.  CE 7.5 fails the same row:
  ``getmodulebyname("$proces")`` misses, the ``getAddressFromName``
  fallback misses, and the aobscanmodule handler raises
  rsAAModuleNotFound, aborting the whole program at parse time
  (autoassembler.pas L1073-1145, read-only reference; no ``$proces``
  special case exists anywhere in CE).  The block is the table's own
  defect, not a CT2Trainer gap.
- DS2 KeyHandlerThread (3 rows: 87499 / 87501 / 87512, providers 87498 /
  87500 / 87511): the Lua providers' static AA envelope releases the
  externally owned KeyHandlerThread — the documented 11-row cluster; the
  prefixed WP-37 handover refusal.
- DS2 g_Instance (1 row: 26341 "freecam_enabled", provider 26340): the
  provider references g_Instance, registered nowhere in the table — the
  actionable per-symbol report (import it as a user symbol, or add a
  record that registers it).
- DS2 InventoryItemProperties_call_dest (1 row: 25364): the symbol is a
  bare call target in the table source only (raw lines 1179 / 1200) —
  never registered, no record / Lua / user-symbol provider — the generic
  refusal wording via the api_call_targets branch, NOT the
  missing-definition report.
- ForgottonAnne usemono (3 rows: 5 / 6 / 103891, provider 0 "Enable"):
  the provider uses usemono(), which targets a Cheat Engine newer than
  7.5 — out of parity scope by design (the documented usemono class).
- RiftApart HeroHealthVFTable (2 rows: 1031 / 1032, provider 1030 "Modify
  Damage Packet"): the provider references HeroHealthVFTable, registered
  in the real table only by encoded embedded-Lua with a createThread
  entry point — out of scope by design (RT-5G: no thread backend ships);
  the actionable per-symbol report stays the named refusal, and the
  documented static-import remedy is what the counter-proof pins.
"""
import tempfile
import unittest
from pathlib import Path

from test_native_compiler import script_record, value_record
from ct2trainer.native.compiler import compile_table, validate_plan

PROCESS = "ct2p21.exe"


def write_table(directory: Path, body: str, name: str = "p21.ct") -> Path:
    path = Path(directory) / name
    path.write_text('<CheatTable CheatEngineTableVersion="52"><CheatEntries>'
                    + body + '</CheatEntries></CheatTable>',
                    encoding="utf-8")
    return path


def by_id(plan: dict) -> dict:
    return {entry["id"]: entry for entry in plan["entries"]}


class P21Base(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)


# ---------------------------------------------------------------------------
# Cluster 1: Cronos pBase (WP-37 handover, plain program record)
# ---------------------------------------------------------------------------

# Owner record 1: live-registered pBase (the external owner).
P21_PBASE_OWNER = (
    "[ENABLE]\n"
    "define(pBase, 0x1000)\n"
    "registersymbol(pBase)\n"
    "[DISABLE]\n"
    "unregistersymbol(pBase)\n"
)

# Provider record 2 (the real 1337261940 shape): provides gun, references
# pBase, and releases pBase on disable — the WP-37 cross-record hazard.
P21_PBASE_PROVIDER = (
    "[ENABLE]\n"
    "aobscan(gunAOB, 8B BE B0 02 00 00 E8)\n"
    "assert(gunAOB, 8B BE B0 02 00 00 E8)\n"
    "alloc(gunBkp, 6)\n"
    "alloc(gun, 8)\n"
    "registersymbol(gun)\n"
    "mov rax, pBase\n"
    "gunBkp:\n"
    "readmem(gunAOB, 6)\n"
    "gunAOB:\n"
    "jmp gunBkp\n"
    "nop\n"
    "[DISABLE]\n"
    "gunAOB:\n"
    "readmem(gunBkp, 6)\n"
    "unregistersymbol(gun)\n"
    "unregistersymbol(pBase)\n"
    "dealloc(gun)\n"
    "dealloc(gunBkp)\n"
)

# Same provider minus the external release: the documented remedy.
P21_PBASE_PROVIDER_CLEAN = P21_PBASE_PROVIDER.replace(
    "unregistersymbol(pBase)\n", "")


class CronosPBaseClusterTests(P21Base):
    def test_provider_release_of_externally_owned_pbase_is_the_named_handover(self):
        # Real rows 1337270007 / 1337264117 / 1337264120 (symbol gun).
        body = (script_record(1, P21_PBASE_OWNER, "pBase owner")
                + script_record(2, P21_PBASE_PROVIDER, "gun provider")
                + value_record(3, "gun+4")
                + value_record(4, "gun+8")
                + value_record(5, "gun+12"))
        plan = compile_table(write_table(self.root, body), PROCESS)
        e = by_id(plan)
        self.assertTrue(e[1]["supported"], e[1]["reason"])
        self.assertFalse(e[2]["supported"])
        self.assertEqual(
            e[2]["reason"],
            "Program may not unregister or deallocate the externally "
            "owned symbol pBase (owned by record 1).")
        for entry_id in (3, 4, 5):
            self.assertFalse(e[entry_id]["supported"])
            self.assertEqual(
                e[entry_id]["reason"],
                "Required symbol has no unique supported provider: gun.")
        validate_plan(plan)

    def test_dependents_resolve_once_the_provider_stops_releasing_pbase(self):
        body = (script_record(1, P21_PBASE_OWNER, "pBase owner")
                + script_record(2, P21_PBASE_PROVIDER_CLEAN, "gun provider")
                + value_record(3, "gun+4")
                + value_record(4, "gun+8")
                + value_record(5, "gun+12"))
        plan = compile_table(write_table(self.root, body, "p21-clean.ct"),
                             PROCESS)
        e = by_id(plan)
        self.assertTrue(e[2]["supported"], e[2]["reason"])
        self.assertEqual(e[2]["provides"], ["gun"])
        for entry_id in (3, 4, 5):
            self.assertTrue(e[entry_id]["supported"], e[entry_id]["reason"])
            self.assertEqual(e[entry_id]["dependency_ids"], [2])
        validate_plan(plan)


# ---------------------------------------------------------------------------
# Cluster 2: Cyberpunk2077 healthPtr (table typo that CE also fails)
# ---------------------------------------------------------------------------

def health_ptr_provider(module: str) -> str:
    return (
        "[ENABLE]\n"
        f"aobscanmodule(health1, {module}, 8B BE B0 02 00 00 E8)\n"
        "assert(health1, 8B BE B0 02 00 00 E8)\n"
        "alloc(health1Bkp, $1000, health1)\n"
        "label(healthPtr)\n"
        "health1Bkp:\n"
        "readmem(health1, 6)\n"
        "health1:\n"
        "jmp health1Bkp\n"
        "nop\n"
        "align 10\n"
        "healthPtr:\n"
        "dq 0\n"
        "registersymbol(health1)\n"
        "registersymbol(health1Bkp)\n"
        "registersymbol(healthPtr)\n"
        "[DISABLE]\n"
        "health1:\n"
        "readmem(health1Bkp, 6)\n"
        "unregistersymbol(health1)\n"
        "unregistersymbol(health1Bkp)\n"
        "unregistersymbol(healthPtr)\n"
        "dealloc(health1Bkp)\n"
    )


class CyberpunkHealthPtrClusterTests(P21Base):
    def test_proces_module_typo_blocks_the_provider_and_cascades(self):
        # Real rows 273 / 274 / 275 / 594; provider 259 "Health Pointer".
        # The aobscanmodule line is program line 2, so the refusal carries
        # the exact real-table "Line 2" wording.
        body = (script_record(1, health_ptr_provider("$proces"),
                              "Health Pointer")
                + value_record(2, "healthPtr+4")
                + value_record(3, "healthPtr+8")
                + value_record(4, "healthPtr+12")
                + value_record(5, "healthPtr+16"))
        plan = compile_table(write_table(self.root, body), PROCESS)
        e = by_id(plan)
        self.assertFalse(e[1]["supported"])
        self.assertEqual(
            e[1]["reason"],
            "Quoted atom '$proces' must be a module basename (.exe/.dll). "
            "Native assembly: Line 2: Quoted atom '$proces' must be a "
            "module basename (.exe/.dll).")
        for entry_id in (2, 3, 4, 5):
            self.assertFalse(e[entry_id]["supported"])
            self.assertEqual(
                e[entry_id]["reason"],
                "Required symbol has no unique supported provider: "
                "healthPtr.")
        validate_plan(plan)

    def test_correct_module_spelling_resolves_the_cluster(self):
        # Counter-proof: the typo is the table's own defect.  With the
        # module atom spelled correctly the provider loads and every
        # dependent resolves — no hidden second gate behind the typo.
        body = (script_record(1, health_ptr_provider(PROCESS),
                              "Health Pointer")
                + value_record(2, "healthPtr+4")
                + value_record(3, "healthPtr+8")
                + value_record(4, "healthPtr+12")
                + value_record(5, "healthPtr+16"))
        plan = compile_table(write_table(self.root, body, "p21-hp.ct"),
                             PROCESS)
        e = by_id(plan)
        self.assertTrue(e[1]["supported"], e[1]["reason"])
        self.assertIn("healthPtr", e[1]["provides"])
        for entry_id in (2, 3, 4, 5):
            self.assertTrue(e[entry_id]["supported"], e[entry_id]["reason"])
            self.assertEqual(e[entry_id]["dependency_ids"], [1])
        validate_plan(plan)


# ---------------------------------------------------------------------------
# Cluster 3: DS2 KeyHandlerThread (Lua static-AA envelope, prefixed)
# ---------------------------------------------------------------------------

# Owner record 1: live-registered KeyHandlerThread.
P21_KHT_OWNER = (
    "[ENABLE]\n"
    "define(KeyHandlerThread, 0x1000)\n"
    "registersymbol(KeyHandlerThread)\n"
    "[DISABLE]\n"
    "unregistersymbol(KeyHandlerThread)\n"
)


def kht_lua_provider(symbol: str, release_external: bool) -> str:
    # The real 87498 / 87500 / 87511 shape: ENABLE Lua registers the value
    # symbol, the static {$asm} envelope is a byte patch, and the static
    # disable envelope releases the externally owned KeyHandlerThread.
    release = "unregistersymbol(KeyHandlerThread)\n" if release_external else ""
    return (
        "[ENABLE]\n"
        "{$lua}\n"
        f"registerSymbol('{symbol}', 0x2000)\n"
        "{$asm}\n"
        f"{PROCESS}+40:\n"
        "db 01\n"
        "[DISABLE]\n"
        "{$lua}\n"
        f"unregisterSymbol('{symbol}')\n"
        "{$asm}\n"
        f"{PROCESS}+40:\n"
        "db 00\n"
        + release
    )


class DS2KeyHandlerThreadClusterTests(P21Base):
    def test_lua_envelope_release_of_keyhandlertthread_is_the_prefixed_handover(self):
        # Real rows 87499 (fValue) / 87501 (dwValue) / 87512
        # (DSVehicleMotorbike); providers 87498 / 87500 / 87511.
        body = (script_record(1, P21_KHT_OWNER, "KeyHandlerThread owner")
                + script_record(2, kht_lua_provider("fValue", True),
                                "FValue provider")
                + script_record(3, kht_lua_provider("dwValue", True),
                                "DwValue provider")
                + script_record(4, kht_lua_provider("DSVehicleMotorbike",
                                                    True),
                                "Motorbike provider")
                + value_record(5, "fValue+4")
                + value_record(6, "dwValue+4")
                + value_record(7, "DSVehicleMotorbike+4"))
        plan = compile_table(write_table(self.root, body), PROCESS)
        e = by_id(plan)
        self.assertTrue(e[1]["supported"], e[1]["reason"])
        for entry_id in (2, 3, 4):
            self.assertFalse(e[entry_id]["supported"])
            self.assertEqual(
                e[entry_id]["reason"],
                "Static AA envelope: Program may not unregister or "
                "deallocate the externally owned symbol KeyHandlerThread "
                "(owned by record 1).")
        for entry_id, symbol in ((5, "fValue"), (6, "dwValue"),
                                 (7, "DSVehicleMotorbike")):
            self.assertFalse(e[entry_id]["supported"])
            self.assertEqual(
                e[entry_id]["reason"],
                f"Required symbol has no unique supported provider: "
                f"{symbol}.")
        validate_plan(plan)

    def test_dependents_resolve_without_the_external_release(self):
        body = (script_record(1, P21_KHT_OWNER, "KeyHandlerThread owner")
                + script_record(2, kht_lua_provider("fValue", False),
                                "FValue provider")
                + script_record(3, kht_lua_provider("dwValue", False),
                                "DwValue provider")
                + script_record(4, kht_lua_provider("DSVehicleMotorbike",
                                                    False),
                                "Motorbike provider")
                + value_record(5, "fValue+4")
                + value_record(6, "dwValue+4")
                + value_record(7, "DSVehicleMotorbike+4"))
        plan = compile_table(write_table(self.root, body, "p21-kht.ct"),
                             PROCESS)
        e = by_id(plan)
        for entry_id, symbol in ((2, "fValue"), (3, "dwValue"),
                                 (4, "DSVehicleMotorbike")):
            self.assertTrue(e[entry_id]["supported"], e[entry_id]["reason"])
            self.assertEqual(e[entry_id]["provides"], [symbol])
        for entry_id, owner in ((5, 2), (6, 3), (7, 4)):
            self.assertTrue(e[entry_id]["supported"], e[entry_id]["reason"])
            self.assertEqual(e[entry_id]["dependency_ids"], [owner])
        validate_plan(plan)


# ---------------------------------------------------------------------------
# Cluster 4: DS2 g_Instance (provider blocked by the named report)
# ---------------------------------------------------------------------------

P21_GINSTANCE_PROVIDER = (
    "[ENABLE]\n"
    "define(freecam_enabled, g_Instance+10)\n"
    "registersymbol(freecam_enabled)\n"
    "[DISABLE]\n"
    "unregistersymbol(freecam_enabled)\n"
)

P21_GINSTANCE_IMPORT = (
    "[ENABLE]\n"
    "define(g_Instance, 0x3000)\n"
    "registersymbol(g_Instance)\n"
    "[DISABLE]\n"
    "unregistersymbol(g_Instance)\n"
)


class DS2GInstanceClusterTests(P21Base):
    def test_provider_of_unregistered_g_instance_gets_the_named_report(self):
        # Real row 26341 "freecam_enabled"; provider 26340.
        body = (script_record(1, P21_GINSTANCE_PROVIDER,
                              "freecam provider")
                + value_record(2, "freecam_enabled+4"))
        plan = compile_table(write_table(self.root, body), PROCESS)
        e = by_id(plan)
        self.assertFalse(e[1]["supported"])
        self.assertEqual(
            e[1]["reason"],
            "Required symbol 'g_Instance' is not registered anywhere in "
            "this table (referenced by 'freecam provider'): no record "
            "defines it and it is not a user-defined symbol. Import it "
            "as a user symbol with its target address, or add a record "
            "that registers it (registersymbol/registerSymbol/label/"
            "aobscan).")
        self.assertFalse(e[2]["supported"])
        self.assertEqual(
            e[2]["reason"],
            "Required symbol has no unique supported provider: "
            "freecam_enabled.")
        validate_plan(plan)

    def test_dependent_resolves_once_g_instance_is_registered(self):
        body = (script_record(1, P21_GINSTANCE_PROVIDER,
                              "freecam provider")
                + script_record(2, P21_GINSTANCE_IMPORT,
                                "g_Instance import")
                + value_record(3, "freecam_enabled+4"))
        plan = compile_table(write_table(self.root, body, "p21-gi.ct"),
                             PROCESS)
        e = by_id(plan)
        self.assertTrue(e[1]["supported"], e[1]["reason"])
        self.assertTrue(e[3]["supported"], e[3]["reason"])
        self.assertEqual(e[3]["dependency_ids"], [1])
        validate_plan(plan)


# ---------------------------------------------------------------------------
# Cluster 5: DS2 InventoryItemProperties_call_dest (bare call target)
# ---------------------------------------------------------------------------

# The real 25364 shape: the record's own program carries the bare call
# target; the symbol is registered nowhere, so the raw-source survey
# classifies it as a call target and the generic wording stays.
P21_CALL_TARGET_RECORD = (
    f"[ENABLE]\n"
    f"{PROCESS}+40:\n"
    "call InventoryItemProperties_call_dest\n"
    "db 90\n"
    f"[DISABLE]\n"
    f"{PROCESS}+40:\n"
    "db 90 90 90 90 90 90\n"
)

P21_CALL_TARGET_IMPORT = (
    "[ENABLE]\n"
    "define(InventoryItemProperties_call_dest, 0x4000)\n"
    "registersymbol(InventoryItemProperties_call_dest)\n"
    "[DISABLE]\n"
    "unregistersymbol(InventoryItemProperties_call_dest)\n"
)


class DS2BareCallTargetClusterTests(P21Base):
    def test_bare_call_target_keeps_the_generic_wording(self):
        # Real row 25364: never registered anywhere, only a bare call
        # target in the table source — the generic refusal, NOT the
        # missing-definition report.
        plan = compile_table(
            write_table(self.root,
                        script_record(1, P21_CALL_TARGET_RECORD,
                                      "Cargo Management")),
            PROCESS)
        e = by_id(plan)
        self.assertFalse(e[1]["supported"])
        self.assertEqual(
            e[1]["reason"],
            "Required symbol has no unique supported provider: "
            "InventoryItemProperties_call_dest.")
        self.assertNotIn("not registered anywhere", e[1]["reason"])
        validate_plan(plan)

    def test_record_resolves_once_the_symbol_is_registered(self):
        plan = compile_table(
            write_table(self.root,
                        script_record(1, P21_CALL_TARGET_RECORD,
                                      "Cargo Management")
                        + script_record(2, P21_CALL_TARGET_IMPORT,
                                        "call dest import"),
                        "p21-call.ct"),
            PROCESS)
        e = by_id(plan)
        self.assertTrue(e[1]["supported"], e[1]["reason"])
        self.assertEqual(e[1]["dependency_ids"], [2])
        validate_plan(plan)


# ---------------------------------------------------------------------------
# Cluster 6: ForgottonAnne usemono (out of parity scope by design)
# ---------------------------------------------------------------------------

def usemono_provider(with_usemono: bool) -> str:
    # The real record 0 "Enable" shape: the line comment on line 2,
    # usemono() on line 3 (the real refusal wording is "Line 3"), and the
    # aobscan after the guard.  The data dialect reaches usemono() before
    # any program-only directive, so the bounded half of the first-pass
    # wrap carries the clean usemono refusal, exactly as in the real
    # table.
    guard = ("usemono()\n" if with_usemono
             else "//(counter-proof) usemono() removed\n")
    return (
        "[ENABLE]\n"
        "//code from here to '[DISABLE]' will be used to enable the cheat\n"
        + guard
        + "aobscan(pPlayerAOB, 8B BE B0 02 00 00 E8)\n"
        "alloc(pPlayerAOBBkp, 6)\n"
        "label(pPlayerBehaviour)\n"
        "label(pArca)\n"
        "pPlayerAOBBkp:\n"
        "readmem(pPlayerAOB, 6)\n"
        "pPlayerAOB:\n"
        "jmp pPlayerAOBBkp\n"
        "nop\n"
        "align 10\n"
        "pPlayerBehaviour:\n"
        "dq 0\n"
        "pArca:\n"
        "dq 0\n"
        "registersymbol(pPlayerAOB)\n"
        "registersymbol(pPlayerAOBBkp)\n"
        "registersymbol(pPlayerBehaviour)\n"
        "registersymbol(pArca)\n"
        "[DISABLE]\n"
        "pPlayerAOB:\n"
        "readmem(pPlayerAOBBkp, 6)\n"
        "unregistersymbol(pPlayerAOB)\n"
        "unregistersymbol(pPlayerAOBBkp)\n"
        "unregistersymbol(pPlayerBehaviour)\n"
        "unregistersymbol(pArca)\n"
        "dealloc(pPlayerAOBBkp)\n"
    )


class ForgottonAnneUsemonoClusterTests(P21Base):
    def test_usemono_provider_block_cascades_to_three_rows(self):
        # Real rows 5 / 6 (pPlayerBehaviour) and 103891 (pArca).
        body = (script_record(1, usemono_provider(True), "Enable")
                + value_record(2, "pPlayerBehaviour+4")
                + value_record(3, "pPlayerBehaviour+8")
                + value_record(4, "pArca+4"))
        plan = compile_table(write_table(self.root, body), PROCESS)
        e = by_id(plan)
        self.assertFalse(e[1]["supported"])
        self.assertEqual(
            e[1]["reason"],
            "usemono targets a Cheat Engine newer than 7.5; out of "
            "parity scope. Native assembly: Line 3: usemono targets a "
            "Cheat Engine newer than 7.5; out of parity scope.")
        self.assertFalse(e[2]["supported"])
        self.assertEqual(
            e[2]["reason"],
            "Required symbol has no unique supported provider: "
            "pPlayerBehaviour.")
        self.assertFalse(e[3]["supported"])
        self.assertEqual(
            e[3]["reason"],
            "Required symbol has no unique supported provider: "
            "pPlayerBehaviour.")
        self.assertFalse(e[4]["supported"])
        self.assertEqual(
            e[4]["reason"],
            "Required symbol has no unique supported provider: pArca.")
        validate_plan(plan)

    def test_provider_without_usemono_supports_the_rows(self):
        body = (script_record(1, usemono_provider(False), "Enable")
                + value_record(2, "pPlayerBehaviour+4")
                + value_record(3, "pPlayerBehaviour+8")
                + value_record(4, "pArca+4"))
        plan = compile_table(write_table(self.root, body, "p21-fa.ct"),
                             PROCESS)
        e = by_id(plan)
        self.assertTrue(e[1]["supported"], e[1]["reason"])
        for symbol in ("pPlayerBehaviour", "pArca"):
            self.assertIn(symbol, e[1]["provides"])
        for entry_id in (2, 3, 4):
            self.assertTrue(e[entry_id]["supported"], e[entry_id]["reason"])
            self.assertEqual(e[entry_id]["dependency_ids"], [1])
        validate_plan(plan)


# ---------------------------------------------------------------------------
# Cluster 7: RiftApart HeroHealthVFTable (encoded embedded-Lua, out of
# scope; static-import remedy pinned)
# ---------------------------------------------------------------------------

P21_VFTABLE_PROVIDER = (
    "[ENABLE]\n"
    "define(damageMult, HeroHealthVFTable+10)\n"
    "define(bOneHitKill, HeroHealthVFTable+14)\n"
    "registersymbol(damageMult)\n"
    "registersymbol(bOneHitKill)\n"
    "[DISABLE]\n"
    "unregistersymbol(damageMult)\n"
    "unregistersymbol(bOneHitKill)\n"
)

P21_VFTABLE_IMPORT = (
    "[ENABLE]\n"
    "define(HeroHealthVFTable, 0x5000)\n"
    "registersymbol(HeroHealthVFTable)\n"
    "[DISABLE]\n"
    "unregistersymbol(HeroHealthVFTable)\n"
)


class RiftApartHeroHealthVFTableClusterTests(P21Base):
    def test_encoded_lua_symbol_keeps_the_named_report(self):
        # Real rows 1031 / 1032; provider 1030 "Modify Damage Packet".
        # In the real table HeroHealthVFTable is registered only by
        # encoded embedded-Lua with a createThread entry point (out of
        # scope, RT-5G), so the named report is the by-design refusal.
        body = (script_record(1, P21_VFTABLE_PROVIDER,
                              "Modify Damage Packet")
                + value_record(2, "damageMult+4")
                + value_record(3, "bOneHitKill+4"))
        plan = compile_table(write_table(self.root, body), PROCESS)
        e = by_id(plan)
        self.assertFalse(e[1]["supported"])
        self.assertEqual(
            e[1]["reason"],
            "Required symbol 'HeroHealthVFTable' is not registered "
            "anywhere in this table (referenced by 'Modify Damage "
            "Packet'): no record defines it and it is not a user-defined "
            "symbol. Import it as a user symbol with its target address, "
            "or add a record that registers it "
            "(registersymbol/registerSymbol/label/aobscan).")
        for entry_id, symbol in ((2, "damageMult"), (3, "bOneHitKill")):
            self.assertFalse(e[entry_id]["supported"])
            self.assertEqual(
                e[entry_id]["reason"],
                f"Required symbol has no unique supported provider: "
                f"{symbol}.")
        validate_plan(plan)

    def test_static_registration_resolves_the_cluster(self):
        # The documented remedy: import the symbol (user-symbol import or
        # a registering record) — the static-import analogue of the
        # encoded embedded-Lua registration the real table carries.
        body = (script_record(1, P21_VFTABLE_PROVIDER,
                              "Modify Damage Packet")
                + script_record(2, P21_VFTABLE_IMPORT,
                                "HeroHealthVFTable import")
                + value_record(3, "damageMult+4")
                + value_record(4, "bOneHitKill+4"))
        plan = compile_table(write_table(self.root, body, "p21-rf.ct"),
                             PROCESS)
        e = by_id(plan)
        self.assertTrue(e[1]["supported"], e[1]["reason"])
        self.assertEqual(sorted(e[1]["provides"]),
                         ["bOneHitKill", "damageMult"])
        for entry_id in (3, 4):
            self.assertTrue(e[entry_id]["supported"], e[entry_id]["reason"])
            self.assertEqual(e[entry_id]["dependency_ids"], [1])
        validate_plan(plan)


if __name__ == '__main__':
    unittest.main()
