"""Lane C (analysis): BaseAddress user-symbol import proof.

The 80 'BaseAddress' blocked rows of the five UE5 script-template tables
(AtomicHeart v1.2, HellPie v1.0, Oregon v1.1, Scorn v1.0, The Callisto
Protocol v1.2 -- roadmap class d: "BaseAddress probed: no Delphi
handling -- user/Lua symbol") are blocked by design until the user
imports the symbol; the block message names the remedy ("Import it as a
user symbol with its target address, or add a record that registers
it").  This dedicated file proves the documented import path
end-to-end on the synthetic script-template shape: the same rows
blocked with the exact named message while BaseAddress is undefined,
fully supported (and NOT staged -- the UDS address is static) once a
<UserdefinedSymbols> BaseAddress entry exists, resolved byte-exactly
through the engine.  The WP-46 UDS zero-candidate fallback in
compiler._dependencies (no supported record provides BaseAddress, so
the table map covers the requirement without a record dependency) is
the path the real-table audit exercises; the lane report carries the
as-is / injected audit evidence (blocked-catalog-043-tgc zero delta).
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

# The synthetic table mirrors the five real tables' "script templates"
# shape: one bound process, a POINTER group with the "4 ways to make a
# pointer point to the same location" rows (nested expression row,
# root-offset row, nested-entry rows) and a Value Types row with a
# relative child.  The pointer chain is read(Base)+30, read+20,
# read+10, read+30 -> final 4-byte value 1234; the Value Types row
# reads read(Base)+20 (the qword there is 0x100000200) and its
# relative child reads that qword +10 (dword 99).
CHAIN_BASE = 0x100000000

TEMPLATE_BODY = """
<CheatEntry><ID>1000</ID><Description>Activation</Description>
<GroupHeader>1</GroupHeader><CheatEntries>
<CheatEntry><ID>1010</ID><Description>POINTER</Description>
<GroupHeader>1</GroupHeader><CheatEntries>
<CheatEntry><ID>1020</ID>
<Description>4 ways to make a pointer point to the same location</Description>
<GroupHeader>1</GroupHeader><CheatEntries>
<CheatEntry><ID>1030</ID><Description>1</Description>
<GroupHeader>1</GroupHeader><CheatEntries>
<CheatEntry><ID>1040</ID><Description>My Value</Description>
<VariableType>4 Bytes</VariableType>
<Address>[[[[BaseAddress]+30]+20]+10]+30</Address>
</CheatEntry></CheatEntries></CheatEntry>
<CheatEntry><ID>1050</ID><Description>2</Description>
<GroupHeader>1</GroupHeader><CheatEntries>
<CheatEntry><ID>1060</ID><Description>My Value</Description>
<VariableType>4 Bytes</VariableType><Address>BaseAddress</Address>
<Offsets><Offset>30</Offset><Offset>10</Offset>
<Offset>20</Offset><Offset>30</Offset></Offsets>
</CheatEntry></CheatEntries></CheatEntry>
<CheatEntry><ID>1100</ID><Description>3</Description>
<GroupHeader>1</GroupHeader><CheatEntries>
<CheatEntry><ID>1110</ID><Description>P1</Description>
<VariableType>8 Bytes</VariableType><Address>BaseAddress</Address>
<Offsets><Offset>30</Offset></Offsets>
<CheatEntries>
<CheatEntry><ID>1112</ID><Description>P2</Description>
<VariableType>8 Bytes</VariableType><Address>+0</Address>
<Offsets><Offset>20</Offset></Offsets>
<CheatEntries>
<CheatEntry><ID>1114</ID><Description>P3</Description>
<VariableType>8 Bytes</VariableType><Address>+0</Address>
<Offsets><Offset>10</Offset></Offsets>
<CheatEntries>
<CheatEntry><ID>1116</ID><Description>My Value</Description>
<VariableType>4 Bytes</VariableType><Address>+0</Address>
<Offsets><Offset>30</Offset></Offsets>
</CheatEntry></CheatEntries>
</CheatEntry></CheatEntries>
</CheatEntry></CheatEntries>
</CheatEntry></CheatEntries>
</CheatEntry></CheatEntries>
</CheatEntry>
<CheatEntry><ID>1200</ID><Description>Name</Description>
<VariableType>8 Bytes</VariableType><Address>BaseAddress</Address>
<Offsets><Offset>20</Offset></Offsets>
<CheatEntries>
<CheatEntry><ID>1202</ID><Description>Length</Description>
<VariableType>4 Bytes</VariableType><Address>+0</Address>
<Offsets><Offset>10</Offset></Offsets>
</CheatEntry></CheatEntries>
</CheatEntry>
</CheatEntries></CheatEntry>
</CheatEntries></CheatEntry>
"""

VALUE_IDS = (1040, 1060, 1110, 1112, 1114, 1116, 1200, 1202)

REMEDY = ("no record defines it and it is not a user-defined symbol. "
          "Import it as a user symbol with its target address, or add a "
          "record that registers it (registersymbol/registerSymbol/"
          "label/aobscan).")


def uds_entry(name: str, address: str) -> str:
    return (f"<SymbolEntry><Name>{xml.sax.saxutils.escape(name)}</Name>"
            f"<Address>{xml.sax.saxutils.escape(address)}</Address></SymbolEntry>")


def template_ct(uds: str) -> str:
    return ('<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
            + TEMPLATE_BODY
            + "</CheatEntries>" + uds + "</CheatTable>")


class ChainMemory:
    """Owned fixture memory: the module base doubles as the imported
    BaseAddress user-symbol value, with the pointer chain laid out
    inside the owned buffer."""

    def __init__(self, pid=123, creation_time=456):
        self.pid, self.creation_time = pid, creation_time
        self.pointer_size = 8
        self.alive, self.closed = True, False
        self.base = CHAIN_BASE
        self.data = bytearray(0x300)
        self.writes = []
        # read(Base) -> 0x100000050; read(0x50+30) -> 0x100000090;
        # read(0x90+20) -> 0x1000000C0; read(0xC0+10) -> 0x100000100;
        # final value at 0x100+30 is 1234; the Value Types pointer at
        # 0x70 is 0x100000200 with dword 99 at 0x210.
        self.data[0x0:0x8] = struct.pack("<Q", CHAIN_BASE + 0x50)
        self.data[0x80:0x88] = struct.pack("<Q", CHAIN_BASE + 0x90)
        self.data[0xB0:0xB8] = struct.pack("<Q", CHAIN_BASE + 0xC0)
        self.data[0xD0:0xD8] = struct.pack("<Q", CHAIN_BASE + 0x100)
        self.data[0x130:0x134] = struct.pack("<I", 1234)
        self.data[0x70:0x78] = struct.pack("<Q", CHAIN_BASE + 0x200)
        self.data[0x210:0x214] = struct.pack("<I", 99)

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
        import re as _re
        symbols = {key.casefold(): value for key, value in (symbols or {}).items()}
        match = _re.fullmatch(
            r'("[^"]+"|[A-Za-z_][\w.]*|[0-9a-fA-F]+)(?:([+-])([0-9a-fA-F]+))?',
            expression)
        if match is None:
            raise OSError("Invalid expression: " + expression)
        base, sign, offset = match.groups()
        if base.strip('"').casefold() == PROCESS.casefold():
            result = self.base
        elif base.casefold() in symbols:
            result = symbols[base.casefold()]
        else:
            try:
                result = int(base, 16)
            except ValueError as exc:
                raise OSError("Unknown symbol: " + base) from exc
        return result + (int(offset, 16) * (-1 if sign == "-" else 1)
                         if offset else 0)

    def resolve_pointer(self, expression, offsets, symbols=None):
        address = self.resolve(expression, symbols)
        for offset in reversed(offsets):
            address = int.from_bytes(self.read(address, self.pointer_size),
                                     "little") + offset
        return address


def _paths() -> dict[int, str]:
    base = "Activation / POINTER / 4 ways to make a pointer point to the same location"
    return {
        1040: base + " / 1 / My Value",
        1060: base + " / 2 / My Value",
        1110: base + " / 3 / P1",
        1112: base + " / 3 / P1 / P2",
        1114: base + " / 3 / P1 / P2 / P3",
        1116: base + " / 3 / P1 / P2 / P3 / My Value",
        1200: "Activation / POINTER / Name",
        1202: "Activation / POINTER / Name / Length",
    }


class BaseAddressAsIsBlockTests(unittest.TestCase):
    """With BaseAddress undefined, every template row is blocked with the
    exact named class-d message (the residual the shipped tables carry)."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="ct2-lanec-asis-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        path = self.root / "baseaddress-as-is.ct"
        path.write_text(template_ct("<UserdefinedSymbols/>"), encoding="utf-8")
        self.plan = compile_table(str(path), PROCESS)
        self.by_id = {entry["id"]: entry for entry in self.plan["entries"]}

    def test_all_eight_template_rows_blocked_with_the_named_message(self):
        for entry_id, path in _paths().items():
            entry = self.by_id[entry_id]
            self.assertFalse(entry["supported"],
                             entry_id and entry["reason"])
            expected = ("Required symbol 'BaseAddress' is not registered "
                        "anywhere in this table (referenced by '%s'): "
                        % path) + REMEDY
            self.assertEqual(entry["reason"], expected,
                             f"row {entry_id} reason mismatch")

    def test_counts_and_headings_stay_supported(self):
        counts = self.plan["counts"]
        self.assertEqual(counts["total"], 14)
        self.assertEqual(counts["headings"], 6)
        self.assertEqual(counts["blocked"], 8)
        self.assertEqual(counts["supported"], 6)
        self.assertEqual(counts["actionable"], 0)
        for entry in self.plan["entries"]:
            if entry["kind"] == "heading":
                self.assertTrue(entry["supported"], entry["reason"])
        # An empty UDS section stays byte-stable: no plan field.
        self.assertNotIn("user_defined_symbols", self.plan)


class BaseAddressImportPlanTests(unittest.TestCase):
    """With a <UserdefinedSymbols> BaseAddress entry, the same rows are
    supported, unstaged and free of record dependencies (WP-46
    zero-candidate fallback: no supported record provides the symbol)."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="ct2-lanec-uds-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        path = self.root / "baseaddress-uds.ct"
        path.write_text(
            template_ct("<UserdefinedSymbols>"
                        + uds_entry("BaseAddress", "100000000")
                        + "</UserdefinedSymbols>"),
            encoding="utf-8")
        self.plan = compile_table(str(path), PROCESS)
        self.by_id = {entry["id"]: entry for entry in self.plan["entries"]}

    def test_all_eight_template_rows_supported_unstaged_without_dependencies(self):
        for entry_id in VALUE_IDS:
            entry = self.by_id[entry_id]
            self.assertTrue(entry["supported"], entry["reason"])
            self.assertFalse(entry.get("staged"),
                             f"row {entry_id} must be unstaged (static UDS address)")
            self.assertEqual(entry["dependency_ids"], [])
            self.assertEqual(entry["requires"], ["BaseAddress"])
        counts = self.plan["counts"]
        self.assertEqual(counts["total"], 14)
        self.assertEqual(counts["headings"], 6)
        self.assertEqual(counts["blocked"], 0)
        self.assertEqual(counts["supported"], 14)
        self.assertEqual(counts["actionable"], 8)

    def test_plan_carries_the_casefolded_uds_map_and_passes_both_validators(self):
        self.assertEqual(self.plan["user_defined_symbols"],
                         {"baseaddress": 0x100000000})
        validate_plan(self.plan)
        validate_runtime_plan(self.plan)

    def test_forced_out_of_range_uds_value_refused_by_both_validators(self):
        import copy
        forged = copy.deepcopy(self.plan)
        forged["user_defined_symbols"] = {"baseaddress": 1 << 64}
        with self.assertRaisesRegex(NativeCompileError, "64-bit unsigned"):
            validate_plan(forged)
        with self.assertRaisesRegex(NativeRuntimeError, "64-bit unsigned"):
            validate_runtime_plan(forged)

    def test_forced_duplicate_casefold_uds_key_refused_by_both_validators(self):
        import copy
        forged = copy.deepcopy(self.plan)
        forged["user_defined_symbols"] = {"BaseAddress": 0x100000000,
                                          "baseaddress": 0x200000000}
        with self.assertRaisesRegex(NativeCompileError,
                                    "Duplicate user-defined symbol name"):
            validate_plan(forged)
        with self.assertRaisesRegex(NativeRuntimeError,
                                    "Duplicate user-defined symbol name"):
            validate_runtime_plan(forged)


class BaseAddressImportEngineTests(unittest.TestCase):
    """Plan -> engine -> byte-exact reads on the owned fixture memory:
    the engine seeds the runtime symbol table from the plan's UDS map
    and resolves every template row (expression form, root-offset form,
    nested relative chain, relative child) through it."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="ct2-lanec-eng-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.shared = self.root / "shared"
        path = self.root / "baseaddress-uds.ct"
        path.write_text(
            template_ct("<UserdefinedSymbols>"
                        + uds_entry("BaseAddress", "100000000")
                        + "</UserdefinedSymbols>"),
            encoding="utf-8")
        self.plan = compile_table(str(path), PROCESS)
        self.memory = ChainMemory()
        self.engine = TrainerEngine(
            self.plan, self.root / "state",
            lambda _name: self.memory, self.shared)
        self.engine.poll()
        self.assertTrue(self.engine.connected, self.engine.status)

    def tearDown(self):
        self.memory.alive = False
        self.engine.poll()
        self.engine.close()

    def test_engine_seeds_baseaddress_from_the_plan_uds_map(self):
        self.assertEqual(self.engine.symbols.get("baseaddress"),
                         0x100000000)

    def test_all_four_pointer_rows_read_byte_exact_through_the_chain(self):
        # Row 1 (nested expression), row 2 (root + offset list) and the
        # deepest nested row all resolve the same chain and read the
        # same final 4 bytes.
        self.assertEqual(self.engine.read_value(1040), "1234")
        self.assertEqual(self.engine.read_value(1060), "1234")
        self.assertEqual(self.engine.read_value(1116), "1234")
        self.assertEqual(self.memory.read(CHAIN_BASE + 0x130, 4),
                         struct.pack("<I", 1234))
        # The Value Types pair: the 8-byte row reads the qword at
        # read(Base)+20; the relative child reads that qword +10.
        self.assertEqual(self.engine.read_value(1200), "4294967808")
        self.assertEqual(self.engine.read_value(1202), "99")
        # Reads never write.
        self.assertEqual(self.memory.writes, [])

    def test_set_value_roundtrip_is_byte_exact(self):
        self.assertEqual(self.engine.set_value(1040, "777"), "777")
        self.assertEqual(self.memory.read(CHAIN_BASE + 0x130, 4),
                         struct.pack("<I", 777))
        self.assertEqual(self.engine.read_value(1040), "777")
        self.assertEqual(self.memory.read(CHAIN_BASE + 0x130, 4),
                         struct.pack("<I", 777))
