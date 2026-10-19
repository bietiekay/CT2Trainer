"""WP-52: Lua broker scan/utility surface on seeded fixture memory.

Covers the record-Lua scan/utility surface the record broker previously
left un-exposed:

- ``memscan.Result`` / ``memscan.OnlyOneResult`` (CE TMemScan property
  contract: Result is the single found address as an integer, nil
  otherwise; OnlyOneResult is the read/write single-result flag).
- ``firstScan(...)`` with a nil rounding argument (CE maps nil through
  lua_tointeger to 0 = rtRounded) plus the miss path where the found list
  is empty and ``Result`` is nil.
- Found-list ``getCount()`` / ``getAddress(i)`` methods (CE LuaFoundlist
  contract: 0-based rows, 8-digit uppercase hexadecimal, the zero address
  for an out-of-bounds row).
- ``createStringlist()`` / ``createStringList()`` with ``.add`` and the
  bounded CE TStrings utility surface (0-based ordinals).
- The ``fullAccess(address, size)`` memory-protection report (CE returns a
  plain boolean; a failing range answers false).
- Unknown globals stay under the named Lua refusal, and the existing
  record-Lua scan API (AOBScan, Count, Address[i]) is byte-identical.

Class-method calls use the CE dot form (the CE luaclass binding carries
the object in an upvalue, so arguments start at the first explicit
parameter); every call is fail-closed with a named reason.
"""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from ct2trainer.native.compiler import compile_table
from ct2trainer.native.engine import TrainerEngine
from ct2trainer.native.lua_host import LuaHostError
from test_native_engine import FakeMemory

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "windows" / "fixture_target" / "fixture.ct"

SCAN_ARGS = ('soExactValue,vtByteArray,nil,"%s",nil,'
             'getAddress("FixtureTarget.exe"),'
             'getAddress("FixtureTarget.exe")+getModuleSize("FixtureTarget.exe"),'
             '"+W-C",fsmNotAligned,"",true,false,false,false')


class ScanMemory(FakeMemory):
    """Seeded fixture memory with a deterministic exact-byte scan backend."""

    @property
    def identity(self):
        return self.pid, self.creation_time

    def _range(self, address, size):
        if not self.base <= address <= self.base + len(self.data) - size:
            raise ValueError("Invalid address")

    def scan_matches(self, pattern, **options):
        self.scan_options = options
        raw = bytes.fromhex(pattern.replace("*", "?").replace(" ", ""))
        start = options.get("start", self.base)
        end = options.get("end", self.base + len(self.data))
        return [self.base + i for i in range(len(self.data) - len(raw) + 1)
                if self.data[i:i + len(raw)] == raw
                and start <= self.base + i < end]


class ScanBrokerTests(unittest.TestCase):
    def setUp(self):
        self.memory = ScanMemory()
        # Two occurrences of the AA BB marker (0x1050, 0x1060) and one
        # unique four-byte marker (0x1078) mirror the corpus one-shot
        # provider shape.
        self.memory.data[80:82] = b"\xaa\xbb"
        self.memory.data[96:98] = b"\xaa\xbb"
        self.memory.data[120:124] = b"\x99\x88\x77\x66"
        self.plan = compile_table(FIXTURE, "FixtureTarget.exe")
        self.engines = []
        self.directories = []

    def tearDown(self):
        for engine in self.engines:
            if not engine.closed:
                self.memory.alive = False
                engine.close()
                self.memory.alive = True
        for directory in self.directories:
            directory.cleanup()

    def host(self):
        """A fresh engine + owned Lua session (one per call, isolated dirs)."""
        directory = tempfile.TemporaryDirectory()
        self.directories.append(directory)
        engine = TrainerEngine(
            self.plan, state_dir=Path(directory.name),
            memory_factory=lambda name: self.memory,
            process_lock_dir=Path(directory.name) / "shared")
        self.engine = engine
        self.engines.append(engine)
        engine.poll()
        engine.toggle(0, True)

        def mutation(action, args):
            if action == "write":
                self.memory.write(*args)
                return True
            if action == "registerSymbol":
                engine.symbols[args[0].casefold()] = args[1]
                return True
            if action == "unregisterSymbol":
                del engine.symbols[args[0].casefold()]
                return True
            raise AssertionError(action)
        return engine.open_lua_session(mutation_handler=mutation)

    # firstScan: nil rounding + hit ---------------------------------------

    def test_first_scan_nil_rounding_hit_populates_found_list(self):
        host = self.host()
        result = host.execute(
            'local m=createMemScan(); local f=createFoundList(m); '
            'm.firstScan(' + SCAN_ARGS % "AA BB" + '); '
            'm.waitTillDone(); f.initialize(); '
            'local n=f.getCount(); local a0=f.getAddress(0); local a1=f.getAddress(1); '
            'local r=m.Result; m.destroy(); f.destroy(); return n,a0,a1,r')
        # Two matches: getCount exact, getAddress 0-based 8-digit hex,
        # Result stays nil for a multi-result scan without the flag.
        self.assertEqual(result, (2, "00001050", "00001060", None))
        self.assertEqual(self.memory.scan_options["protection"], "+W-C")

    def test_first_scan_miss_returns_nil_result_and_zero_count(self):
        host = self.host()
        result = host.execute(
            'local m=createMemScan(); '
            'local r=m.firstScan(' + SCAN_ARGS % "DE AD BE EF" + '); '
            'm.waitTillDone(); '
            'local taken = (r==nil); '
            'local single = (m.Result==nil); '
            'local f=createFoundList(m); f.initialize(); '
            'local n=f.getCount(); local z=f.getAddress(0); '
            'm.destroy(); f.destroy(); return taken,single,n,z')
        # CE: firstScan answers nil, an empty scan leaves Result nil, and
        # an out-of-bounds row of an empty list reports the zero address.
        self.assertEqual(result, (True, True, 0, "00000000"))

    # memscan.Result / OnlyOneResult --------------------------------------

    def test_result_returns_single_address_as_integer_and_registers_symbol(self):
        host = self.host()
        result = host.execute(
            'local m=createMemScan(); '
            'm.firstScan(' + SCAN_ARGS % "99 88 77 66" + '); '
            'm.waitTillDone(); '
            'local r=m.Result; '
            'if r then registerSymbol("P3Base", r) end; '
            'm.destroy(); '
            'return r, getAddressOfSymbol("P3Base")')
        # The one-shot provider shape: the unique marker resolves to the
        # exact integer address and registerSymbol accepts it.
        self.assertEqual(result, (0x1078, 0x1078))

    def test_only_one_result_flag_and_first_result_semantics(self):
        host = self.host()
        result = host.execute(
            'local m=createMemScan(); '
            'local default=m.OnlyOneResult; '
            'm.OnlyOneResult=true; '
            'local flag=m.OnlyOneResult; '
            'm.firstScan(' + SCAN_ARGS % "AA BB" + '); '
            'm.waitTillDone(); '
            'local r=m.Result; '
            'm.destroy(); '
            'return default,flag,r')
        # Default false; the flag round-trips; with the flag set, Result
        # answers the first found address (CE OnlyOne first-hit contract).
        self.assertEqual(result, (False, True, 0x1050))

    def test_result_requires_a_single_match_without_the_flag(self):
        host = self.host()
        two = host.execute(
            'local m=createMemScan(); '
            'm.firstScan(' + SCAN_ARGS % "AA BB" + '); '
            'm.waitTillDone(); local r=m.Result; m.destroy(); return r')
        self.assertIsNone(two)
        host = self.host()
        miss = host.execute(
            'local m=createMemScan(); '
            'm.firstScan(' + SCAN_ARGS % "DE AD BE EF" + '); '
            'm.waitTillDone(); local r=m.Result; m.destroy(); return r')
        self.assertIsNone(miss)

    def test_scan_property_refusals_stay_named(self):
        host = self.host()
        with self.assertRaisesRegex(LuaHostError,
                                    "Unsupported memory scan property: Bother"):
            host.execute('return createMemScan().Bother')
        with self.assertRaisesRegex(
                LuaHostError, "Memory scan property is outside this profile"):
            host.execute('createMemScan().Progress=5')
        with self.assertRaisesRegex(LuaHostError,
                                    "Memory scan is destroyed"):
            host.execute('local m=createMemScan(); m.destroy(); return m.Result')

    # found list -----------------------------------------------------------

    def test_get_address_out_of_bounds_answers_zero_address(self):
        host = self.host()
        result = host.execute(
            'local m=createMemScan(); local f=createFoundList(m); '
            'm.firstScan(' + SCAN_ARGS % "AA BB" + '); '
            'm.waitTillDone(); f.initialize(); '
            'local hi=f.getAddress(5); local lo=f.getAddress(-1); local none=f.getAddress(); '
            'm.destroy(); f.destroy(); return hi,lo,none')
        # CE contract: out-of-bounds rows answer the zero address, an
        # argument-less call answers nil.
        self.assertEqual(result, ("00000000", "00000000", None))

    def test_found_list_methods_refuse_invalid_state(self):
        host = self.host()
        with self.assertRaisesRegex(LuaHostError,
                                    "Found list is not initialized"):
            host.execute(
                'local m=createMemScan(); local f=createFoundList(m); '
                'm.firstScan(' + SCAN_ARGS % "AA BB" + '); '
                'm.waitTillDone(); return f.getCount()')
        with self.assertRaisesRegex(LuaHostError, "Invalid found list index"):
            host.execute(
                'local m=createMemScan(); local f=createFoundList(m); '
                'm.firstScan(' + SCAN_ARGS % "AA BB" + '); '
                'm.waitTillDone(); f.initialize(); '
                'return f.getAddress("0")')
        with self.assertRaisesRegex(
                LuaHostError, "Found list memory scan is destroyed"):
            host.execute(
                'local m=createMemScan(); local f=createFoundList(m); '
                'm.firstScan(' + SCAN_ARGS % "AA BB" + '); '
                'm.waitTillDone(); f.initialize(); '
                'm.destroy(); return f.getCount()')
        with self.assertRaisesRegex(
                LuaHostError, "Unsupported found list property: getCountX"):
            host.execute(
                'local m=createMemScan(); local f=createFoundList(m); '
                'm.firstScan(' + SCAN_ARGS % "AA BB" + '); '
                'm.waitTillDone(); f.initialize(); '
                'return f.getCountX()')

    # firstScan refusals ----------------------------------------------------

    def test_first_scan_refusals_keep_named_reasons(self):
        host = self.host()
        with self.assertRaisesRegex(LuaHostError, "fourteen"):
            host.execute('createMemScan().firstScan("AA BB")')
        with self.assertRaisesRegex(
                LuaHostError, "Unsupported scan rounding type: rtTruncated"):
            host.execute(
                'createMemScan().firstScan(soExactValue,vtByteArray,'
                '"rtTruncated","AA BB",nil,getAddress("FixtureTarget.exe"),'
                'getAddress("FixtureTarget.exe")+getModuleSize("FixtureTarget.exe"),'
                '"+W-C",fsmNotAligned,"",true,false,false,false)')
        with self.assertRaisesRegex(
                LuaHostError, "symbolic API constants"):
            host.execute(
                'createMemScan().firstScan("soNextValue",vtByteArray,nil,'
                '"AA BB",nil,getAddress("FixtureTarget.exe"),'
                'getAddress("FixtureTarget.exe")+getModuleSize("FixtureTarget.exe"),'
                '"+W-C",fsmNotAligned,"",true,false,false,false)')
        with self.assertRaisesRegex(
                LuaHostError, "Unsupported exact byte-array scan options"):
            host.execute(
                'createMemScan().firstScan(soExactValue,vtByteArray,nil,'
                '"AA BB",123,getAddress("FixtureTarget.exe"),'
                'getAddress("FixtureTarget.exe")+getModuleSize("FixtureTarget.exe"),'
                '"+W-C",fsmNotAligned,"",true,false,false,false)')

    # string list -----------------------------------------------------------

    def test_create_stringlist_add_and_iteration(self):
        host = self.host()
        result = host.execute(
            'local l=createStringlist(); '
            'local i0=l.add("alpha"); '
            'local i1=l.add(42); '
            'local c=l.getCount(); '
            'local t0=l.getString(0); local t1=l.String[1]; local d0=l[0]; '
            'local alias=createStringList(); local ac=alias.add("beta"); '
            'return i0,i1,c,t0,t1,d0,alias.getCount()')
        # add() answers the new 0-based ordinal; numbers coerce to text;
        # the capital-L spelling is an owned alias of the same object.
        self.assertEqual(result, (0, 1, 2, "alpha", "42", "alpha", 1))

    def test_stringlist_mutation_surface(self):
        host = self.host()
        result = host.execute(
            'local l=createStringlist(); '
            'l.add("one"); l.add("two"); l.add("three"); '
            'local ins=l.insert(1,"TWO"); '
            'local mid=l[1]; '
            'local found=l.indexOf("tWo"); '
            'l.remove("two"); '
            'local after=l.getCount(); '
            'l.delete(0); '
            'l.setString(0,"last"); '
            'local last=l.getString(0); '
            'l.beginUpdate(); l.endUpdate(); '
            'l.clear(); '
            'return mid,found,after,last,l.getCount()')
        # insert is 0-based; the default CE comparison is case-insensitive;
        # remove deletes by value; beginUpdate/endUpdate pair cleanly.
        self.assertEqual(result, ("TWO", 1, 3, "last", 0))

    def test_stringlist_case_sensitive_lookup(self):
        host = self.host()
        result = host.execute(
            'local l=createStringlist(); '
            'l.add("Mixed"); '
            'local case=l.indexOf("mixed"); '
            'l.setCaseSensitive(true); '
            'local strict=l.indexOf("mixed"); '
            'local flag=l.CaseSensitive; '
            'return case,strict,flag')
        # CE default: case-insensitive ordinal compare; opt-in strictness.
        self.assertEqual(result, (0, -1, True))

    def test_stringlist_refusals_stay_named(self):
        host = self.host()
        with self.assertRaisesRegex(
                LuaHostError, "String list index out of range"):
            host.execute('return createStringlist().getString(0)')
        with self.assertRaisesRegex(
                LuaHostError, "String list object data is outside this profile"):
            host.execute('local l=createStringlist(); l.add("x",1234)')
        with self.assertRaisesRegex(
                LuaHostError, "String list file access is outside this profile"):
            host.execute('local l=createStringlist(); l.loadFromFile("c:/x.txt")')
        with self.assertRaisesRegex(
                LuaHostError, "String list object data is outside this profile"):
            host.execute('local l=createStringlist(); l.getData(0)')
        with self.assertRaisesRegex(
                LuaHostError, "Unsupported string list property: FullAccess"):
            host.execute('return createStringlist().FullAccess')
        with self.assertRaisesRegex(
                LuaHostError, "String list property is outside this profile"):
            host.execute('local l=createStringlist(); l.Sort=true')
        with self.assertRaisesRegex(
                LuaHostError, "String list update is not open"):
            host.execute('local l=createStringlist(); l.endUpdate()')

    # fullAccess ------------------------------------------------------------

    def test_full_access_reports_booleans_for_ranges(self):
        host = self.host()
        result = host.execute(
            'local ok=fullAccess(getAddress("FixtureTarget.exe"),16); '
            'local bad=fullAccess(getAddress("FixtureTarget.exe")+250,16); '
            'local sym=fullAccess("FixtureTarget.exe+10",8); '
            'return ok,bad,sym')
        # CE contract: a valid bounded range answers true, a failing range
        # answers false (no error), and expression addresses resolve.
        self.assertEqual(result, (True, False, True))

    def test_full_access_refusals_keep_named_reasons(self):
        host = self.host()
        with self.assertRaisesRegex(
                LuaHostError, "fullAccess requires exactly two arguments"):
            host.execute('return fullAccess("1000")')
        with self.assertRaisesRegex(
                LuaHostError, "fullAccess size is outside 1..4 MiB"):
            host.execute('return fullAccess("1000",5*1024*1024)')

    # unknown globals / existing surface -------------------------------------

    def test_unknown_global_keeps_named_lua_refusal(self):
        # WP-56 (lane w4-d): unknown nil globals now surface the exact named
        # refusal instead of the raw Lua nil-call text, so the bootstrap
        # error and the broker catch-all agree on one message.
        host = self.host()
        with self.assertRaisesRegex(
                LuaHostError, "Unsupported CE Lua API: zetaScan"):
            host.execute('return zetaScan("AA BB")')
        # The broker-level catch-all stays intact for routed names.
        broker = self.engine.lua_sessions[-1][1]
        with self.assertRaisesRegex(
                LuaHostError, "Unsupported CE Lua API: zetaScan"):
            broker.call("zetaScan", (), generation=broker.generation,
                        syntaxcheck=False)

    def test_existing_scan_surface_stays_byte_identical(self):
        host = self.host()
        self.assertEqual(
            host.execute('local s=AOBScan("AA BB"); return s.Count,s[0],s[1]'),
            (2, "1050", "1060"))
        self.assertEqual(
            host.execute(
                'local m=createMemScan(); local f=createFoundList(m); '
                'm.firstScan(' + SCAN_ARGS % "AA BB" + '); '
                'm.waitTillDone(); f.initialize(); '
                'local n,a,b=f.Count,f.Address[0],f.Address[1]; '
                'm.destroy(); f.destroy(); return n,a,b'),
            (2, "1050", "1060"))


if __name__ == "__main__":
    unittest.main()
