"""Post-0.50 residual-census ratification (tests only, 0.51 cycle).

The unrated residual classes of the post-0.50 catalog census
(blocked-catalog-050-provider21: 193 rows) that stay blocked by design;
every other residual row is already covered by a documented gate or by a
0.44-0.50 ratification lane.  This file pins, with self-contained
synthetic fixtures mirroring the real-table shapes (no TableReferences,
no CE inputs, no real-table path references - the real-table probing
evidence lives in side/evidence/), for every cluster:

1. the exact block reason as measured in the census,
2. the counter-proof that the rows resolve once the documented
   condition is met - no hidden second gate.

Clusters (real rows in parentheses):

- DS2 KeyHandlerThread (11 rows: 87498 / 87500 / 87502 / 87507 / 87508 /
  87509 / 87510 / 87511 / 87513 / 87514 / 87516): every record allocates
  the SAME symbol name ``KeyHandlerThread`` through a Lua-generated
  ``alloc(KeyHandlerThread, 0x1000, process)`` line (``process`` is the
  CE module-name Lua global, ProcessHandlerUnit.pas L186-189) and
  registers / releases it in the static ``{$asm}`` envelope.  The static
  program never lists the Lua-generated allocation, so each record's
  own ``dealloc`` drops to ``unowned_cleanup_dropped`` in the first
  pass; the 0.42 cleanup-parity re-check then finds the name
  live-registered by every other supported record and re-blocks each
  record with the prefixed WP-37 handover refusal, owner = first other
  entry in entry order (the mutual 87498 <-> 87500 attribution of the
  census).  CE 7.5 breaks the same way at runtime: the later record's
  ``registersymbol`` overwrites the shared name, so the earlier record's
  disable-phase ``dealloc`` frees the later record's live thread block -
  the table is a one-record-at-a-time test harness.  The static model
  cannot prove multi-activation safety, so all 11 rows stay
  fail-closed by design.
- AtomicHeart 73 ("Unlimited Energy"): the DISABLE line
  ``unregistersymbol(energyBkp)dealloc(newmem)`` glues a second
  directive onto the first.  CE 7.5 consumes the whole line at the
  first directive (the unregistersymbol handler, autoassembler.pas
  L2492-2525: first-`)` parse, split, line dropped, ``continue``) and
  silently discards the glued dealloc (a leaked block; the record
  works).  CT2Trainer keeps the named parse refusal - teaching the
  parser to swallow trailing directive content would mask real
  authoring errors.
- P3R-v4 229 ("No money lost weapon/crane?"):
  ``reassemble(moneylost_gain+4,5)`` - CE 7.5 reassemble is
  single-argument (autoassembler.pas L2413-2452;
  rsWrongSyntaxReAssemble = 'Wrong syntax. Reassemble(address)',
  L113); the trailing `,5` breaks the address expression even in CE.
- Cyberpunk2077 159 ("Find Name"): ``assert(true)`` - CE 7.5 assert
  requires the two-argument ``assert(address, bytestring)`` form
  (autoassembler.pas L2023-2030) and raises
  rsWrongSyntaxASSERTAddress1122335566 for the comma-less line; the
  record is a debug helper whose Lua lookup runs first and whose assert
  then fails - broken in CE as well.  The static named refusal is
  correct.
- Sinking City Remastered 258084 ("Fast Travel"): the DISABLE phase
  writes ``bFastTravel: db 0`` to the record's own ENABLE
  ``globalalloc(bFastTravel,1,$process)`` with changed bytes.  In CE
  the global persists session-lifetime and the line is a plain data
  write (the record works); CT2Trainer's O19 shared-global contract
  (RT-4.5, global_alloc.py: a direct global cursor on an initialized
  global in DISABLE starts a reset that must repeat the exact ENABLE
  initializer bytes - equal or empty = CE no-op, changed = named
  changed-reinitialization refusal) deliberately fails closed, because
  the engine's global-pool lifecycle and recovery journal do not
  journal a changed re-initialization.
- Little Kitty Big City (2 rows: 1 / 2): the usemono() directive
  targets a Cheat Engine newer than 7.5 - out of parity scope by
  design, here in the Static AA envelope prefix form (the plain form
  is pinned by the 0.50 ForgottonAnne cluster).
"""
import tempfile
import unittest
from pathlib import Path

from test_native_compiler import script_record
from ct2trainer.native.compiler import compile_table, validate_plan

PROCESS = "ct2resid.exe"


def write_table(directory: Path, body: str, name: str = "resid.ct") -> Path:
    path = Path(directory) / name
    path.write_text('<CheatTable CheatEngineTableVersion="52"><CheatEntries>'
                    + body + '</CheatEntries></CheatTable>',
                    encoding="utf-8")
    return path


def by_id(plan: dict) -> dict:
    return {entry["id"]: entry for entry in plan["entries"]}


class ResidualBase(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)


# ---------------------------------------------------------------------------
# Cluster 1: DS2 KeyHandlerThread provider rows (shared Lua-alloc symbol)
# ---------------------------------------------------------------------------

def kht_record(symbol: str) -> str:
    # The real 87498 / 87500 / ... shape: the alloc line is generated by
    # the record Lua at runtime (dynamic base: the CE ``process`` module
    # name), the static {$asm} envelope registers the shared name and
    # the static disable envelope releases it.
    return (
        "[ENABLE]\n"
        "{$lua}\n"
        f"return [[alloc( {symbol}, 0x1000, ]] .. process .. [[ )]]\n"
        "{$asm}\n"
        f"registersymbol( {symbol} )\n"
        f"CreateThread( {symbol} )\n"
        "label( KeyHandlerOff )\n"
        "registersymbol( KeyHandlerOff )\n"
        "label( fValue )\n"
        "registersymbol( fValue )\n"
        f"{symbol}:\n"
        "mov eax,1\n"
        "[DISABLE]\n"
        "{$lua}\n"
        "return nil\n"
        "{$asm}\n"
        "unregistersymbol(fValue)\n"
        "unregistersymbol(KeyHandlerOff)\n"
        f"unregistersymbol({symbol})\n"
        f"dealloc({symbol})\n"
    )


KHT_REASON = ("Static AA envelope: Program may not unregister or "
              "deallocate the externally owned symbol {symbol} "
              "(owned by record {owner}).")


class DS2KeyHandlerThreadProviderClusterTests(ResidualBase):
    def test_shared_name_blocks_every_record_with_entry_order_ownership(self):
        # Real rows 87498 / 87500 / 87502 / 87507 / 87508 / 87509 /
        # 87510 / 87511 / 87513 / 87514 / 87516 - all eleven allocate the
        # same symbol name and release it on their own disable.
        body = (script_record(10, kht_record("KeyHandlerThread"),
                              "KHT record 1")
                + script_record(11, kht_record("KeyHandlerThread"),
                                "KHT record 2")
                + script_record(12, kht_record("KeyHandlerThread"),
                                "KHT record 3"))
        plan = compile_table(write_table(self.root, body), PROCESS)
        e = by_id(plan)
        for entry_id in (10, 11, 12):
            self.assertFalse(e[entry_id]["supported"],
                             e[entry_id]["reason"])
        self.assertEqual(
            e[10]["reason"],
            KHT_REASON.format(symbol="KeyHandlerThread", owner=11))
        self.assertEqual(
            e[11]["reason"],
            KHT_REASON.format(symbol="KeyHandlerThread", owner=10))
        # the remaining records attribute the ownership to the first
        # entry in entry order - the census "owned by record 87498"
        self.assertEqual(
            e[12]["reason"],
            KHT_REASON.format(symbol="KeyHandlerThread", owner=10))
        validate_plan(plan)

    def test_single_record_stays_supported_without_a_sharing_peer(self):
        # Counter-proof: with no other record registering the same name
        # the record's own release is an in-program cleanup, not a
        # cross-record hazard - no hidden second gate behind the block.
        body = script_record(10, kht_record("KeyHandlerThread"),
                             "KHT record")
        plan = compile_table(write_table(self.root, body, "resid-kht1.ct"),
                             PROCESS)
        e = by_id(plan)
        self.assertTrue(e[10]["supported"], e[10]["reason"])
        self.assertIn("KeyHandlerThread", e[10]["provides"])
        validate_plan(plan)

    def test_unique_symbol_names_resolve_every_record(self):
        # Counter-proof of the documented condition: per-record unique
        # alloc names remove the contention; both records load.
        body = (script_record(10, kht_record("KeyHandlerThreadA"),
                              "KHT record A")
                + script_record(11, kht_record("KeyHandlerThreadB"),
                                "KHT record B"))
        plan = compile_table(write_table(self.root, body, "resid-kht2.ct"),
                             PROCESS)
        e = by_id(plan)
        for entry_id in (10, 11):
            self.assertTrue(e[entry_id]["supported"],
                            e[entry_id]["reason"])
        validate_plan(plan)


# ---------------------------------------------------------------------------
# Cluster 2: AtomicHeart glued directive (CE line-consumption tolerance)
# ---------------------------------------------------------------------------

ATOMICHEART_ENERGY = (
    "[ENABLE]\n"
    "aobscanmodule(energy,$process,48 8B 89 ?? ?? ?? ?? 48 81 C1 28 01 00 00 E9)\n"
    "alloc(newmem,$1000,energy)\n"
    "\n"
    "label(energyBkp)\n"
    "label(return)\n"
    "\n"
    "newmem:\n"
    "\n"
    "energyBkp:\n"
    "  readmem(energy+07,7)\n"
    "  mov [rcx+8],(float)100.0\n"
    "  jmp return\n"
    "\n"
    "energy+07:\n"
    "  jmp newmem\n"
    "  nop 2\n"
    "return:\n"
    "registersymbol(energy)\n"
    "registersymbol(energyBkp)\n"
    "\n"
    "[DISABLE]\n"
    "energy+07:\n"
    "  readmem(energyBkp,7)\n"
    "unregistersymbol(energy)\n"
    "unregistersymbol(energyBkp)dealloc(newmem)\n"
)

# Same record with the glued line split - the documented remedy.
ATOMICHEART_ENERGY_CLEAN = ATOMICHEART_ENERGY.replace(
    "unregistersymbol(energyBkp)dealloc(newmem)\n",
    "unregistersymbol(energyBkp)\ndealloc(newmem)\n")


class AtomicHeartGluedDirectiveClusterTests(ResidualBase):
    def test_glued_disable_directive_keeps_the_named_parse_refusal(self):
        # Real row 73 "Unlimited Energy": the glued dealloc lands on
        # program line 26 in the real table, so the fixture mirrors the
        # exact real line layout and the exact "Line 26" wording.
        body = script_record(1, ATOMICHEART_ENERGY, "Unlimited Energy")
        plan = compile_table(write_table(self.root, body), PROCESS)
        e = by_id(plan)
        self.assertFalse(e[1]["supported"])
        self.assertEqual(
            e[1]["reason"],
            "Unsupported AA directive: alloc. Native assembly: "
            "Line 26: Unbalanced directive arguments.")
        validate_plan(plan)

    def test_split_lines_resolve_the_record(self):
        # Counter-proof: the block is purely the glued-line parse.  With
        # the directives on separate lines the record loads (CE
        # tolerates the glued form only by silently leaking the block).
        body = script_record(1, ATOMICHEART_ENERGY_CLEAN,
                             "Unlimited Energy")
        plan = compile_table(write_table(self.root, body,
                                         "resid-ah73-clean.ct"), PROCESS)
        e = by_id(plan)
        self.assertTrue(e[1]["supported"], e[1]["reason"])
        validate_plan(plan)


# ---------------------------------------------------------------------------
# Cluster 3: P3R-v4 two-argument reassemble (CE single-argument form)
# ---------------------------------------------------------------------------

P3R_MONEYLOST = (
    "{  Game Executable   : P3R.exe\n"
    "   Author            : Tuuup!\n"
    "   Executable Version: \n"
    "   Script Date       : 2024-02-03\n"
    "}\n"
    "[ENABLE]\n"
    "aobscanmodule(moneylost_gain,$process,03??33??E8????????89??????????4883????5BC3????????????4889)\n"
    "registersymbol(moneylost_gain moneylost_gainbkp)\n"
    "alloc(newmem,128,moneylost_gain)\n"
    "label(return)\n"
    "label(moneylost_gainbkp)\n"
    "newmem:\n"
    "cmp edx,#1\n"
    "jge @f\n"
    "xor edx,edx\n"
    "\n"
    "code:\n"
    "  add ecx,edx\n"
    "  xor edx,edx\n"
    "reassemble(moneylost_gain+4,5)  //call P3R.exe.impdata+1087EA0\n"
    "  jmp return\n"
    "  \n"
    "moneylost_gainbkp:\n"
    "readmem(moneylost_gain,9)\n"
    "\n"
    "moneylost_gain:\n"
    "  jmp newmem\n"
    "  nop 4\n"
    "return:\n"
    "\n"
    "[DISABLE]\n"
    "moneylost_gain:\n"
    " // db 03 CA 33 D2 E8 C2 26 EB FF\n"
    "readmem(moneylost_gainbkp,9)\n"
    "unregistersymbol(*)\n"
    "dealloc(*)\n"
)

# Same record with the documented single-argument reassemble.
P3R_MONEYLOST_CLEAN = P3R_MONEYLOST.replace(
    "reassemble(moneylost_gain+4,5)",
    "reassemble(moneylost_gain+4)")


class P3RReassembleClusterTests(ResidualBase):
    def test_two_argument_reassemble_keeps_the_named_refusal(self):
        # Real row 229 "No money lost weapon/crane?": the reassemble
        # line is program line 20 in the real table (comment block and
        # the blank line included), so the fixture mirrors the exact
        # real line layout and the exact "Line 20" wording.
        body = script_record(1, P3R_MONEYLOST,
                             "No money lost weapon/crane?")
        plan = compile_table(write_table(self.root, body), PROCESS)
        e = by_id(plan)
        self.assertFalse(e[1]["supported"])
        self.assertEqual(
            e[1]["reason"],
            "Unsupported AA directive: alloc. Native assembly: "
            "Line 20: reassemble has an invalid argument count.")
        validate_plan(plan)

    def test_single_argument_reassemble_resolves_the_record(self):
        # Counter-proof: the `,5` is the table's own defect; the
        # single-argument form CE accepts loads the record.
        body = script_record(1, P3R_MONEYLOST_CLEAN,
                             "No money lost weapon/crane?")
        plan = compile_table(write_table(self.root, body,
                                         "resid-p3r229-clean.ct"), PROCESS)
        e = by_id(plan)
        self.assertTrue(e[1]["supported"], e[1]["reason"])
        validate_plan(plan)


# ---------------------------------------------------------------------------
# Cluster 4: Cyberpunk2077 one-argument assert (CE two-argument form)
# ---------------------------------------------------------------------------

def cp_find_name(assert_line: str) -> str:
    # The real 159 shape: a debug-helper Lua part (lookup + printf) and a
    # static envelope of a single assert line.  The static envelope is
    # [ENABLE] / assert / [DISABLE], so the assert is program line 2.
    return (
        "[ENABLE]\n"
        "{$lua}\n"
        "return nil\n"
        "{$asm}\n"
        + assert_line +
        "[DISABLE]\n"
    )


CP_FIND_NAME_CLEAN = (
    "[ENABLE]\n"
    "{$lua}\n"
    "return nil\n"
    "{$asm}\n"
    "aobscan(nameAOB, 8B BE B0 02 00 00 E8)\n"
    "assert(nameAOB, 8B BE B0 02 00 00 E8)\n"
    "alloc(nameBkp, 6)\n"
    "nameBkp:\n"
    "readmem(nameAOB, 6)\n"
    "nameAOB:\n"
    "jmp nameBkp\n"
    "nop\n"
    "[DISABLE]\n"
    "nameAOB:\n"
    "readmem(nameBkp, 6)\n"
)


class CyberpunkAssertClusterTests(ResidualBase):
    def test_one_argument_assert_keeps_the_named_refusal(self):
        # Real row 159 "Find Name": the comma-less assert(true) is the
        # static envelope line 2, matching the census wording.
        body = script_record(1, cp_find_name("assert(true)\n"),
                             "Find Name")
        plan = compile_table(write_table(self.root, body), PROCESS)
        e = by_id(plan)
        self.assertFalse(e[1]["supported"])
        self.assertEqual(
            e[1]["reason"],
            "Static AA envelope: Line 2: assert has an invalid "
            "argument count.")
        validate_plan(plan)

    def test_two_argument_assert_resolves_the_record(self):
        # Counter-proof: the two-argument assert(address, bytestring)
        # form CE requires is supported - the one-argument spelling is
        # the table's own defect.
        body = script_record(1, CP_FIND_NAME_CLEAN, "Find Name")
        plan = compile_table(write_table(self.root, body,
                                         "resid-cp159-clean.ct"), PROCESS)
        e = by_id(plan)
        self.assertTrue(e[1]["supported"], e[1]["reason"])
        validate_plan(plan)


# ---------------------------------------------------------------------------
# Cluster 5: Sinking City changed global DISABLE re-initialization (O19)
# ---------------------------------------------------------------------------

def sc2_fast_travel(reset_line: str) -> str:
    # The real 258084 shape: two globalallocs in ENABLE, the
    # bFastTravel global initialized with db 1, and the DISABLE phase
    # writing the global cursor again (the reset under test) plus the
    # scan-symbol byte restore.
    return (
        "[ENABLE]\n"
        "aobscanmodule(FastTravel,$process,C6 80 A1 00 00 00 00 48 C7 80 A8 00 00 00 00 00 00 00 B2)\n"
        "registersymbol(FastTravel)\n"
        "alloc(newmem1,$100,FastTravel)\n"
        "globalalloc(bFastTravel,1,$process)\n"
        "bFastTravel:\n"
        "db 1\n"
        "label(done)\n"
        "newmem1:\n"
        "mov rax,bFastTravel\n"
        "mov [rax],rax\n"
        "jmp done\n"
        "FastTravel:\n"
        "jmp newmem1\n"
        "nop 2\n"
        "done:\n"
        "[DISABLE]\n"
        "bFastTravel:\n"
        + reset_line +
        "FastTravel:\n"
        "db C6 80 A1 00 00 00 00\n"
        "unregistersymbol(FastTravel)\n"
        "dealloc(newmem1)\n"
    )


class SinkingCityGlobalReinitClusterTests(ResidualBase):
    def test_changed_reset_bytes_keep_the_named_refusal(self):
        # Real row 258084 "Fast Travel": the DISABLE resets the
        # initialized global with changed bytes (db 0 vs the ENABLE
        # db 1) - the O19 changed-reinitialization refusal.
        body = script_record(1, sc2_fast_travel("db 0\n"), "Fast Travel")
        plan = compile_table(write_table(self.root, body), PROCESS)
        e = by_id(plan)
        self.assertFalse(e[1]["supported"])
        self.assertEqual(
            e[1]["reason"],
            "Global DISABLE re-initialization must repeat the exact "
            "ENABLE initializer bytes; the changed value stays "
            "blocked: bFastTravel")
        validate_plan(plan)

    def test_equal_reset_bytes_resolve_the_record(self):
        # Counter-proof: repeating the exact ENABLE initializer (the CE
        # no-op the contract models) loads the record - the changed
        # bytes are the only defect.
        body = script_record(1, sc2_fast_travel("db 1\n"), "Fast Travel")
        plan = compile_table(write_table(self.root, body,
                                         "resid-sc2-clean.ct"), PROCESS)
        e = by_id(plan)
        self.assertTrue(e[1]["supported"], e[1]["reason"])
        validate_plan(plan)


# ---------------------------------------------------------------------------
# Cluster 6: Little Kitty usemono envelope form (out of parity scope)
# ---------------------------------------------------------------------------

LITTLEKITTY_ENVELOPE = (
    "usemono()\n"
    "{$lua}\n"
    "return nil\n"
    "{$asm}\n"
    "[ENABLE]\n"
    "mov eax,1\n"
    "[DISABLE]\n"
)

# Same record without the out-of-scope directive.
LITTLEKITTY_ENVELOPE_CLEAN = LITTLEKITTY_ENVELOPE.replace(
    "usemono()\n", "")


class LittleKittyUsemonoEnvelopeClusterTests(ResidualBase):
    def test_envelope_usemono_keeps_the_prefixed_named_refusal(self):
        # Real rows 1 / 2: usemono() on the first static envelope line -
        # the envelope-prefix form of the documented usemono > 7.5
        # refusal (the plain form is pinned by the 0.50 ForgottonAnne
        # cluster).
        body = script_record(1, LITTLEKITTY_ENVELOPE, "Activate")
        plan = compile_table(write_table(self.root, body), PROCESS)
        e = by_id(plan)
        self.assertFalse(e[1]["supported"])
        self.assertEqual(
            e[1]["reason"],
            "Static AA envelope: Line 1: usemono targets a Cheat "
            "Engine newer than 7.5; out of parity scope.")
        validate_plan(plan)

    def test_record_without_usemono_resolves(self):
        # Counter-proof: the refusal is the directive alone.
        body = script_record(1, LITTLEKITTY_ENVELOPE_CLEAN, "Activate")
        plan = compile_table(write_table(self.root, body,
                                         "resid-kitty-clean.ct"), PROCESS)
        e = by_id(plan)
        self.assertTrue(e[1]["supported"], e[1]["reason"])
        validate_plan(plan)
