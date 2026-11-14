"""0.49 (analysis): the remaining class-d value-symbol import ratification.

The 17 residual class-d rows of the post-0.48 catalog census (roadmap
class d: "probed: no Delphi handling -- user/Lua symbol") reference
game-side symbols that no table record registers and that the table
author expects the user to import as user-defined symbols with their
target addresses.  Every one of the 17 is blocked by design with the
exact named message ("Import it as a user symbol with its target
address, or add a record that registers it"); the 0.48 audit carries
the as-is rows:

- 6 x g_GameLibSystemAssets (HorizonForbiddenWest, both file
  instances -- identical row shape, one synthetic instance ratifies
  both), the [ Pointers/Structures ] heading chain;
- 5 x HeroSystem (RiftApart), the HeroSystem -> HeroLocal ->
  HeroHealth / HeroTimeScaleManager / HeroXPManager heading chain
  (the branch rows' 2-hop offset lists flattened into single
  expressions by the compiler);
- 3 x pGrav (YLILWin64): the bare-offset-list row, the nested
  expression row [[pGrav]+20]+18 and the one-dereference row
  [pGrav]+10;
- 2 x MapLastLeftClickCoordinates_Pointer (AtomicHeart v1.2), the
  [symbol]-dereference heading chain;
- 1 x the Kena module-qualified operand
  Kena-Win64-Shipping.UResourcesComponent::FreeResources, whose
  dependency walk names three symbol parts (FreeResources, Kena,
  Win64).

This file proves the documented import path on the synthetic shapes:
the same rows blocked with the exact named message while the symbol is
undefined, fully supported (and NOT staged -- the UDS address is
static) once the <UserdefinedSymbols> entries exist, resolved
byte-exactly through the engine (expression chains and the
offset-list resolve_pointer path).  The WP-46 UDS zero-candidate
fallback in compiler._dependencies (no supported record provides the
symbol, so the table map covers the requirement without a record
dependency) is the path the real-table audit exercises; the lane
report carries the as-is / injected audit evidence
(blocked-catalog-049-variable zero delta on all lanes except the
shape-3 unblocks).

The 2 HeroHealthVFTable rows of RiftApart (921 / 1030) are documented
out of scope: their registration lives in an encoded embedded-Lua
block (loadTableFiles -> findTableFile, Ascii85 <Files>) with a
createThread entry point, not a static symbol import.
"""
from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path
import xml.sax.saxutils

from ct2trainer.native.compiler import (NativeCompileError, compile_table,
                                        validate_plan)
from ct2trainer.native.engine import (NativeRuntimeError, TrainerEngine,
                                      validate_plan as validate_runtime_plan)

PROCESS = "FixtureTarget.exe"

# The synthetic table mirrors the four real value-symbol shapes under
# one root group:
# - the HorizonFW heading chain (heading root Address=g_GameLibSystemAssets
#   + the +0 / +0+80 / +0+88 leaves, 8 Bytes, hex display);
# - the RiftApart heading chain (HeroSystem -> HeroLocal ->
#   HeroHealth / HeroTimeScaleManager / HeroXPManager, the 5 leaves);
# - the YLIL direct rows (offset list, nested expression, one deref);
# - the AtomicHeart [symbol]-dereference heading chain (2 float leaves).
# UDS addresses: g_GameLibSystemAssets = base+0x000, HeroSystem =
# base+0x100, pGrav = base+0x400,
# MapLastLeftClickCoordinates_Pointer = base+0x500.
BASE = 0x140000000

TEMPLATE_BODY = """
<CheatEntry><ID>1000</ID><Description>Pointers</Description>
<GroupHeader>1</GroupHeader><CheatEntries>
<CheatEntry><ID>1100</ID><Description>g_GameLibSystemAssets</Description>
<GroupHeader>1</GroupHeader><ShowAsHex>1</ShowAsHex>
<Address>g_GameLibSystemAssets</Address><CheatEntries>
<CheatEntry><ID>1200</ID><Description>g_GameLibSystemAssets</Description>
<VariableType>8 Bytes</VariableType><Address>+0</Address>
<ShowAsSigned>1</ShowAsSigned><ShowAsHex>1</ShowAsHex></CheatEntry>
<CheatEntry><ID>1210</ID><Description>[0080] PlayerLoadoutManagerResource</Description>
<VariableType>8 Bytes</VariableType><Address>+0</Address>
<Offsets><Offset>80</Offset></Offsets>
<ShowAsSigned>1</ShowAsSigned><ShowAsHex>1</ShowAsHex></CheatEntry>
<CheatEntry><ID>1220</ID><Description>[0088] DifficultyManagerResource</Description>
<VariableType>8 Bytes</VariableType><Address>+0</Address>
<Offsets><Offset>88</Offset></Offsets>
<ShowAsSigned>1</ShowAsSigned><ShowAsHex>1</ShowAsHex></CheatEntry>
</CheatEntries></CheatEntry>
<CheatEntry><ID>1300</ID><Description>HeroSystem</Description>
<GroupHeader>1</GroupHeader><Address>HeroSystem</Address>
<Offsets><Offset>0</Offset></Offsets><CheatEntries>
<CheatEntry><ID>1310</ID><Description>HeroLocal</Description>
<GroupHeader>1</GroupHeader><Address>+2C0</Address>
<Offsets><Offset>0</Offset></Offsets><CheatEntries>
<CheatEntry><ID>1320</ID><Description>HeroHealth</Description>
<GroupHeader>1</GroupHeader><Address>+90</Address>
<Offsets><Offset>0</Offset><Offset>78</Offset></Offsets><CheatEntries>
<CheatEntry><ID>1400</ID><Description>Max Health</Description>
<VariableType>Float</VariableType><Address>+80</Address></CheatEntry>
<CheatEntry><ID>1410</ID><Description>Current Health</Description>
<VariableType>Float</VariableType><Address>+88</Address></CheatEntry>
<CheatEntry><ID>1420</ID><Description>Disable Enemy Attacking?</Description>
<VariableType>Byte</VariableType><Address>+AC</Address>
<ShowAsHex>1</ShowAsHex></CheatEntry>
</CheatEntries></CheatEntry>
<CheatEntry><ID>1330</ID><Description>HeroTimeScaleManager</Description>
<GroupHeader>1</GroupHeader><Address>+90</Address>
<Offsets><Offset>0</Offset><Offset>A0</Offset></Offsets><CheatEntries>
<CheatEntry><ID>1430</ID><Description>Timescale Multiplier</Description>
<VariableType>Float</VariableType><Address>+B8</Address></CheatEntry>
</CheatEntries></CheatEntry>
<CheatEntry><ID>1340</ID><Description>HeroXPManager</Description>
<GroupHeader>1</GroupHeader><Address>+90</Address>
<Offsets><Offset>0</Offset><Offset>1F8</Offset></Offsets><CheatEntries>
<CheatEntry><ID>1440</ID><Description>Current XP</Description>
<VariableType>4 Bytes</VariableType><Address>+48</Address></CheatEntry>
</CheatEntries></CheatEntry>
</CheatEntries></CheatEntry>
</CheatEntries></CheatEntry>
<CheatEntry><ID>1500</ID><Description>Physics</Description>
<GroupHeader>1</GroupHeader><CheatEntries>
<CheatEntry><ID>1600</ID><Description>Activ</Description>
<VariableType>Float</VariableType><Address>pGrav</Address>
<Offsets><Offset>18</Offset><Offset>20</Offset></Offsets></CheatEntry>
<CheatEntry><ID>1610</ID><Description>No description</Description>
<VariableType>Float</VariableType><Address>[[pGrav]+20]+18</Address></CheatEntry>
<CheatEntry><ID>1620</ID><Description>No description</Description>
<VariableType>Float</VariableType><Address>[pGrav]+10</Address></CheatEntry>
</CheatEntries></CheatEntry>
<CheatEntry><ID>1700</ID><Description>MapCoordinates</Description>
<GroupHeader>1</GroupHeader><Address>[MapLastLeftClickCoordinates_Pointer]</Address>
<ShowAsHex>1</ShowAsHex><CheatEntries>
<CheatEntry><ID>1800</ID><Description>MapLastLeftClick.X</Description>
<VariableType>Float</VariableType><Address>+03A0</Address></CheatEntry>
<CheatEntry><ID>1810</ID><Description>MapLastLeftClick.Y</Description>
<VariableType>Float</VariableType><Address>+03A4</Address></CheatEntry>
</CheatEntries></CheatEntry>
</CheatEntries>
</CheatEntry>
"""

VALUE_IDS = (1200, 1210, 1220, 1400, 1410, 1420, 1430, 1440,
             1600, 1610, 1620, 1800, 1810)

REMEDY = ("no record defines it and it is not a user-defined symbol. "
          "Import it as a user symbol with its target address, or add a "
          "record that registers it (registersymbol/registerSymbol/"
          "label/aobscan).")

# row id -> (required symbol, as-is "referenced by" path)
AS_IS_REASONS = {
    1200: ("g_GameLibSystemAssets",
           "Pointers / g_GameLibSystemAssets / g_GameLibSystemAssets"),
    1210: ("g_GameLibSystemAssets",
           "Pointers / g_GameLibSystemAssets / [0080] "
           "PlayerLoadoutManagerResource"),
    1220: ("g_GameLibSystemAssets",
           "Pointers / g_GameLibSystemAssets / [0088] "
           "DifficultyManagerResource"),
    1400: ("HeroSystem",
           "Pointers / HeroSystem / HeroLocal / HeroHealth / Max Health"),
    1410: ("HeroSystem",
           "Pointers / HeroSystem / HeroLocal / HeroHealth / "
           "Current Health"),
    1420: ("HeroSystem",
           "Pointers / HeroSystem / HeroLocal / HeroHealth / "
           "Disable Enemy Attacking?"),
    1430: ("HeroSystem",
           "Pointers / HeroSystem / HeroLocal / HeroTimeScaleManager / "
           "Timescale Multiplier"),
    1440: ("HeroSystem",
           "Pointers / HeroSystem / HeroLocal / HeroXPManager / "
           "Current XP"),
    1600: ("pGrav", "Pointers / Physics / Activ"),
    1610: ("pGrav", "Pointers / Physics / No description"),
    1620: ("pGrav", "Pointers / Physics / No description"),
    1800: ("MapLastLeftClickCoordinates_Pointer",
           "Pointers / MapCoordinates / MapLastLeftClick.X"),
    1810: ("MapLastLeftClickCoordinates_Pointer",
           "Pointers / MapCoordinates / MapLastLeftClick.Y"),
}


def uds_entry(name: str, address: str) -> str:
    return (f"<SymbolEntry><Name>{xml.sax.saxutils.escape(name)}</Name>"
            f"<Address>{xml.sax.saxutils.escape(address)}</Address></SymbolEntry>")


def template_ct(uds: str) -> str:
    return ('<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
            + TEMPLATE_BODY
            + "</CheatEntries>" + uds + "</CheatTable>")


def full_uds() -> str:
    return ("<UserdefinedSymbols>"
            + uds_entry("g_GameLibSystemAssets", "140000000")
            + uds_entry("HeroSystem", "140000100")
            + uds_entry("pGrav", "140000400")
            + uds_entry("MapLastLeftClickCoordinates_Pointer", "140000500")
            + "</UserdefinedSymbols>")


class ValueSymbolAsIsBlockTests(unittest.TestCase):
    """While the four symbols are undefined, every value row is blocked
    with the exact named class-d message (the residual the shipped
    tables carry)."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(
            prefix="ct2-classd-asis-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        path = self.root / "classd-as-is.ct"
        path.write_text(template_ct("<UserdefinedSymbols/>"),
                        encoding="utf-8")
        self.plan = compile_table(str(path), PROCESS)
        self.by_id = {entry["id"]: entry for entry in self.plan["entries"]}

    def test_all_thirteen_rows_blocked_with_the_named_message(self):
        for entry_id, (symbol, path) in AS_IS_REASONS.items():
            entry = self.by_id[entry_id]
            self.assertFalse(entry["supported"],
                             entry_id and entry["reason"])
            expected = ("Required symbol '%s' is not registered anywhere "
                        "in this table (referenced by '%s'): " % (symbol,
                                                                 path)
                        ) + REMEDY
            self.assertEqual(entry["reason"], expected,
                             f"row {entry_id} reason mismatch")
            self.assertEqual(entry["requires"], [symbol])

    def test_counts_and_headings_stay_supported(self):
        counts = self.plan["counts"]
        self.assertEqual(counts["total"], 22)
        self.assertEqual(counts["headings"], 9)
        self.assertEqual(counts["blocked"], 13)
        self.assertEqual(counts["supported"], 9)
        self.assertEqual(counts["actionable"], 0)
        for entry in self.plan["entries"]:
            if entry["kind"] == "heading":
                self.assertTrue(entry["supported"], entry["reason"])
        # An empty UDS section stays byte-stable: no plan field.
        self.assertNotIn("user_defined_symbols", self.plan)


class ValueSymbolImportPlanTests(unittest.TestCase):
    """With the four <UserdefinedSymbols> entries, the same rows are
    supported, unstaged and free of record dependencies (WP-46
    zero-candidate fallback: no supported record provides a symbol)."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="ct2-classd-uds-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        path = self.root / "classd-uds.ct"
        path.write_text(template_ct(full_uds()), encoding="utf-8")
        self.plan = compile_table(str(path), PROCESS)
        self.by_id = {entry["id"]: entry for entry in self.plan["entries"]}

    def test_all_thirteen_rows_supported_unstaged_without_dependencies(self):
        for entry_id in VALUE_IDS:
            entry = self.by_id[entry_id]
            self.assertTrue(entry["supported"], entry["reason"])
            self.assertFalse(entry.get("staged"),
                             f"row {entry_id} must be unstaged "
                             "(static UDS address)")
            self.assertEqual(entry["dependency_ids"], [])
            self.assertEqual(entry["requires"],
                             [AS_IS_REASONS[entry_id][0]])
        counts = self.plan["counts"]
        self.assertEqual(counts["total"], 22)
        self.assertEqual(counts["headings"], 9)
        self.assertEqual(counts["blocked"], 0)
        self.assertEqual(counts["supported"], 22)
        self.assertEqual(counts["actionable"], 13)

    def test_plan_carries_the_casefolded_uds_map_and_passes_both_validators(self):
        self.assertEqual(self.plan["user_defined_symbols"], {
            "g_gamelibsystemassets": 0x140000000,
            "herosystem": 0x140000100,
            "pgrav": 0x140000400,
            "maplastleftclickcoordinates_pointer": 0x140000500,
        })
        validate_plan(self.plan)
        validate_runtime_plan(self.plan)

    def test_forced_out_of_range_uds_value_refused_by_both_validators(self):
        import copy
        forged = copy.deepcopy(self.plan)
        forged["user_defined_symbols"]["pgrav"] = 1 << 64
        with self.assertRaisesRegex(NativeCompileError, "64-bit unsigned"):
            validate_plan(forged)
        with self.assertRaisesRegex(NativeRuntimeError, "64-bit unsigned"):
            validate_runtime_plan(forged)

    def test_forced_duplicate_casefold_uds_key_refused_by_both_validators(self):
        import copy
        forged = copy.deepcopy(self.plan)
        forged["user_defined_symbols"] = dict(self.plan["user_defined_symbols"])
        forged["user_defined_symbols"]["PGrav"] = 0x240000000
        with self.assertRaisesRegex(
                NativeCompileError, "Duplicate user-defined symbol name"):
            validate_plan(forged)
        with self.assertRaisesRegex(
                NativeRuntimeError, "Duplicate user-defined symbol name"):
            validate_runtime_plan(forged)


class ValueChainMemory:
    """Owned fixture memory: the four UDS addresses sit inside the owned
    buffer and every chain hop (the flattened expression reads and the
    offset-list resolve_pointer path) stays in-buffer.

    Horizon:  read(U_H) = P_H; value at P_H+0x80 / P_H+0x88.
    Rift:     read(U_S) = P1; read(P1+0x2C0) = P2; read(P2+0x90) = P3;
              read(P3+0x78) = HH0 (health leaves), read(P3+0xA0) =
              TS0 (timescale leaf), read(P3+0x1F8) = XP0 (xp leaf).
    YLIL:     read(U_G) = G0; read(G0+0x20) = G1; value at G1+0x18
              (rows 1600 + 1610), at G0+0x10 (row 1620).
    Atomic:   read(U_M) = MH0; value at MH0+0x3A0 / MH0+0x3A4.
    """

    def __init__(self, pid=123, creation_time=456):
        self.pid, self.creation_time = pid, creation_time
        self.pointer_size = 8
        self.alive, self.closed = True, False
        self.base = BASE
        self.data = bytearray(0x1000)
        self.writes = []
        self.data[0x000:0x008] = struct.pack("<Q", BASE + 0x010)  # P_H
        self.data[0x090:0x098] = struct.pack("<Q", 0xAAAABBBBCCCCDDDD)
        self.data[0x098:0x0A0] = struct.pack("<Q", 0x1122334455667788)
        self.data[0x100:0x108] = struct.pack("<Q", BASE + 0x110)  # P1
        self.data[0x3D0:0x3D8] = struct.pack("<Q", BASE + 0x120)  # P2
        self.data[0x1B0:0x1B8] = struct.pack("<Q", BASE + 0x140)  # P3
        self.data[0x1B8:0x1C0] = struct.pack("<Q", BASE + 0x150)  # HH0
        self.data[0x1D0:0x1D4] = struct.pack("<f", 1.25)  # Max Health
        self.data[0x1D8:0x1DC] = struct.pack("<f", 2.5)  # Current Health
        self.data[0x1FC:0x1FD] = b"\x02"  # Disable Enemy Attacking
        self.data[0x1E0:0x1E8] = struct.pack("<Q", BASE + 0x180)  # TS0
        self.data[0x238:0x23C] = struct.pack("<f", 0.5)  # Timescale
        self.data[0x338:0x340] = struct.pack("<Q", BASE + 0x1A0)  # XP0
        self.data[0x1E8:0x1EC] = struct.pack("<I", 42)  # Current XP
        self.data[0x400:0x408] = struct.pack("<Q", BASE + 0x410)  # G0
        self.data[0x420:0x424] = struct.pack("<f", 5.5)  # row 1620
        self.data[0x430:0x438] = struct.pack("<Q", BASE + 0x440)  # G1
        self.data[0x458:0x45C] = struct.pack("<f", 3.5)  # rows 1600/1610
        self.data[0x500:0x508] = struct.pack("<Q", BASE + 0x510)  # MH0
        self.data[0x8B0:0x8B4] = struct.pack("<f", 6.25)  # .X
        self.data[0x8B4:0x8B8] = struct.pack("<f", 7.5)  # .Y

    @property
    def identity(self):
        return self.pid, self.creation_time

    def is_alive(self):
        return self.alive

    def close(self):
        self.closed = True

    def _range(self, address, size):
        if not self.base <= address or address + size > self.base + len(self.data):
            raise ValueError("Outside owned fixture memory")

    def is_executable(self, address, size):
        return False

    def module(self, name):
        if name.casefold() != PROCESS.casefold():
            raise OSError("Unknown module: " + name)
        return self.base, len(self.data)

    def read(self, address, size):
        self._range(address, size)
        return bytes(self.data[address - self.base:address - self.base + size])

    def write(self, address, raw):
        self._range(address, len(raw))
        self.writes.append((address, bytes(raw)))
        self.data[address - self.base:address - self.base + len(raw)] = raw

    def scan_module(self, name, pattern):
        self.module(name)
        raise OSError("scan not needed for this fixture")

    def resolve(self, expression, symbols=None):
        symbols = {key.casefold(): value for key, value in (symbols or {}).items()}
        name = expression.strip().strip('"')
        if name.casefold() in symbols:
            return symbols[name.casefold()]
        raise OSError("Unknown symbol: " + name)

    def resolve_pointer(self, expression, offsets, symbols=None):
        address = self.resolve(expression, symbols)
        for offset in reversed(offsets):
            address = int.from_bytes(self.read(address, self.pointer_size),
                                     "little") + offset
        return address


class ValueSymbolImportEngineTests(unittest.TestCase):
    """Plan -> engine -> byte-exact reads on the owned fixture memory:
    the engine seeds the runtime symbol table from the plan's UDS map
    and resolves every row (the flattened expression chains and the
    offset-list resolve_pointer path) through it."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="ct2-classd-eng-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.shared = self.root / "shared"
        path = self.root / "classd-uds.ct"
        path.write_text(template_ct(full_uds()), encoding="utf-8")
        self.plan = compile_table(str(path), PROCESS)
        self.memory = ValueChainMemory()
        self.engine = TrainerEngine(
            self.plan, self.root / "state",
            lambda _name: self.memory, self.shared)
        self.engine.poll()
        self.assertTrue(self.engine.connected, self.engine.status)

    def tearDown(self):
        self.memory.alive = False
        self.engine.poll()
        self.engine.close()

    def test_engine_seeds_all_four_symbols_from_the_plan_uds_map(self):
        self.assertEqual(self.engine.symbols.get(
            "g_gamelibsystemassets"), BASE + 0x000)
        self.assertEqual(self.engine.symbols.get("herosystem"),
                         BASE + 0x100)
        self.assertEqual(self.engine.symbols.get("pgrav"), BASE + 0x400)
        self.assertEqual(self.engine.symbols.get(
            "maplastleftclickcoordinates_pointer"), BASE + 0x500)

    def test_thirteen_rows_read_byte_exact_through_the_uds_chains(self):
        # The Horizon chain: +0 reads the pointer itself (hex display,
        # integers carry no zero padding), +0+80 / +0+88 dereference
        # through it.
        self.assertEqual(self.engine.read_value(1200),
                         "140000010")
        self.assertEqual(self.engine.read_value(1210),
                         "AAAABBBBCCCCDDDD")
        self.assertEqual(self.engine.read_value(1220),
                         "1122334455667788")
        # The RiftApart branch chain (2-hop offset lists flattened).
        self.assertEqual(self.engine.read_value(1400), "1.25")
        self.assertEqual(self.engine.read_value(1410), "2.5")
        self.assertEqual(self.engine.read_value(1420), "2")
        self.assertEqual(self.engine.read_value(1430), "0.5")
        self.assertEqual(self.engine.read_value(1440), "42")
        # The YLIL rows: the offset-list row and the nested expression
        # row resolve the same final address; the one-deref row its own.
        self.assertEqual(self.engine.read_value(1600), "3.5")
        self.assertEqual(self.engine.read_value(1610), "3.5")
        self.assertEqual(self.engine.read_value(1620), "5.5")
        # The AtomicHeart dereference heading chain.
        self.assertEqual(self.engine.read_value(1800), "6.25")
        self.assertEqual(self.engine.read_value(1810), "7.5")
        # Reads never write.
        self.assertEqual(self.memory.writes, [])

    def test_set_value_roundtrip_is_byte_exact(self):
        # The Max Health float (the deepest flattened chain).
        self.assertEqual(self.engine.set_value(1400, "9.75"), "9.75")
        self.assertEqual(self.memory.read(BASE + 0x1D0, 4),
                         struct.pack("<f", 9.75))
        self.assertEqual(self.engine.read_value(1400), "9.75")


# The Kena module-qualified operand (the one class-d AA row of the
# 17): the dependency walk decomposes
# Kena-Win64-Shipping.UResourcesComponent::FreeResources into three
# symbol parts (FreeResources, Kena, Win64), probed against the real
# table.  Importing the full managed name as a single UDS does NOT
# cover it (the decomposition is the documented contract) -- the
# progressive remedy names the next missing part each time.
KENA_PROCESS = "Kena-Win64-Shipping.exe"
KENA_BODY = """
<CheatEntry><ID>1</ID><Description>hook</Description>
<GroupHeader>1</GroupHeader><CheatEntries>
<CheatEntry><ID>2</ID><Description>Auto Assemble script</Description>
<VariableType>Auto Assembler Script</VariableType>
<AssemblerScript>[ENABLE]
alloc(newmem,2048,"Kena-Win64-Shipping.exe"+158A4C4)
label(returnhere)
label(originalcode)
label(exit)
newmem:
mov eax,[Kena-Win64-Shipping.UResourcesComponent::FreeResources+8]
originalcode:
jmp exit
"Kena-Win64-Shipping.exe"+158A4C4:
jmp newmem
nop
exit:
returnhere:
[DISABLE]
dealloc(newmem)
"Kena-Win64-Shipping.exe"+158A4C4:
db 8B 05 BE 04 78 04
</AssemblerScript></CheatEntry>
</CheatEntries></CheatEntry>
"""


def kena_ct(uds: str) -> str:
    return ('<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
            + KENA_BODY + "</CheatEntries>"
            + "<UserdefinedSymbols>" + uds + "</UserdefinedSymbols>"
            + "</CheatTable>")


class KenaModuleQualifiedImportTests(unittest.TestCase):
    """Plan level: the module-qualified operand's three-part remedy."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="ct2-kena-uds-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def _plan(self, uds, name):
        path = self.root / ("kena-" + name + ".ct")
        path.write_text(kena_ct(uds), encoding="utf-8")
        plan = compile_table(str(path), KENA_PROCESS)
        return next(e for e in plan["entries"] if e["id"] == 2), plan

    def test_as_is_block_names_the_first_symbol_part(self):
        entry, _plan = self._plan("", "as-is")
        self.assertFalse(entry["supported"])
        expected = ("Required symbol 'FreeResources' is not registered "
                    "anywhere in this table (referenced by 'hook / "
                    "Auto Assemble script'): ") + REMEDY
        self.assertEqual(entry["reason"], expected)
        self.assertEqual(entry["requires"],
                         ["FreeResources", "Kena", "Win64"])

    def test_partial_import_names_the_next_missing_part(self):
        entry, _plan = self._plan(uds_entry("FreeResources", "140000000"),
                                  "free-only")
        self.assertFalse(entry["supported"])
        expected = ("Required symbol 'Kena' is not registered anywhere "
                    "in this table (referenced by 'hook / Auto "
                    "Assemble script'): ") + REMEDY
        self.assertEqual(entry["reason"], expected)

    def test_all_three_parts_supported_unstaged_without_dependencies(self):
        uds = (uds_entry("FreeResources", "140000000")
               + uds_entry("Kena", "140000100")
               + uds_entry("Win64", "140000200"))
        entry, plan = self._plan(uds, "three-parts")
        self.assertTrue(entry["supported"], entry["reason"])
        self.assertFalse(entry.get("staged"))
        self.assertEqual(entry["dependency_ids"], [])
        self.assertEqual(entry["requires"],
                         ["FreeResources", "Kena", "Win64"])
        validate_plan(plan)
        validate_runtime_plan(plan)

    def test_full_managed_name_as_single_uds_stays_blocked(self):
        entry, _plan = self._plan(uds_entry(
            "Kena-Win64-Shipping.UResourcesComponent::FreeResources",
            "140000000"), "full-name")
        self.assertFalse(entry["supported"])
        expected = ("Required symbol 'FreeResources' is not registered "
                    "anywhere in this table (referenced by 'hook / "
                    "Auto Assemble script'): ") + REMEDY
        self.assertEqual(entry["reason"], expected)


if __name__ == "__main__":
    unittest.main()
