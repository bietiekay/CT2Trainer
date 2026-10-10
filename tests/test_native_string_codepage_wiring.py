"""CodePage wiring tests: the pinned contract through the String pipeline.

Verifies that an explicit non-default CT CodePage attribute (1250-1257,
65001) resolves to the pinned stdlib codec in string profiles, survives the
value_types dispatch, compiles in owned CTs, and round-trips through the
engine runtime; that the default (absent or 0) CodePage keeps the legacy
default codecs so the 0.8 owned-fixture pins stay byte-stable; and that
unpinned values, Boolean flags and Unicode combinations are refused
fail-closed with no writes.
"""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from test_native_lua_activation import Memory
from test_native_value_runtime import DataCoordinator
from ct2trainer.native.compiler import compile_table, validate_plan as compiler_validate
from ct2trainer.native.engine import TrainerEngine, NativeRuntimeError, validate_plan
from ct2trainer.native.string_values import (
    StringValueError, desired_matches, format_value, parse, prepare, validate)
from ct2trainer.native.value_types import (
    format_profile_value, parse_profile_value, prepare_value_profile,
    validate_value_profile)


class CpMemory(Memory):
    def __init__(self):
        super().__init__()
        self.protection = 4
        self.writes = []

    def _query(self, address):
        self._range(address, 1)
        return SimpleNamespace(BaseAddress=self.base, AllocationBase=self.base,
            RegionSize=len(self.data), State=0x1000, Protect=self.protection,
            Type=0x20000)


class CodePageProfileTests(unittest.TestCase):
    def test_default_codepage_keeps_legacy_codecs(self):
        default = prepare({'Length': 8})
        self.assertEqual(default['properties']['CodePage'], False)
        self.assertEqual(default['encoding'], 'ascii')
        self.assertEqual(prepare({'Length': 8, 'CodePage': False})['encoding'], 'ascii')
        self.assertEqual(prepare({'Length': 8, 'CodePage': 0})['encoding'], 'ascii')
        self.assertEqual(prepare({'Length': 8, 'CodePage': '0'})['encoding'], 'ascii')
        wide = prepare({'Length': 4, 'Unicode': 1})
        self.assertEqual(wide['encoding'], 'utf-16-le')
        self.assertEqual(wide['unit_bytes'], 2)
        self.assertEqual(wide['size'], 8)
        self.assertEqual(prepare({'Length': 4, 'Unicode': 1, 'CodePage': '0'})['encoding'],
                         'utf-16-le')

    def test_pinned_non_default_codepages_resolve_contract_codecs(self):
        expected = {1250: 'cp1250', 1251: 'cp1251', 1252: 'cp1252',
                    1253: 'cp1253', 1254: 'cp1254', 1257: 'cp1257', 65001: 'utf-8'}
        for value, codec in expected.items():
            with self.subTest(codepage=value):
                profile = prepare({'Length': 16, 'CodePage': value})
                self.assertEqual(profile['encoding'], codec)
                self.assertEqual(profile['unit_bytes'], 1)
                self.assertEqual(profile['size'], 16)
                self.assertEqual(profile['properties']['CodePage'], value)
                self.assertTrue(profile['actionable'])

    def test_xml_string_codepage_values(self):
        profile = prepare({'Length': 8, 'CodePage': ' 1252 '})
        self.assertEqual(profile['properties']['CodePage'], 1252)
        self.assertEqual(profile['encoding'], 'cp1252')

    def test_unpinned_codepages_refused_fail_closed(self):
        for value in (1, 932, 28591, 100000, -1):
            with self.subTest(codepage=value):
                with self.assertRaisesRegex(StringValueError,
                                            'Codepage %d is not in the pinned' % value):
                    prepare({'Length': 8, 'CodePage': value})
        with self.assertRaisesRegex(StringValueError, 'exact integer'):
            prepare({'Length': 8, 'CodePage': True})
        with self.assertRaisesRegex(StringValueError, 'exact integer'):
            prepare({'Length': 8, 'CodePage': '12ab'})

    def test_codepage_refused_with_unicode(self):
        with self.assertRaisesRegex(StringValueError, 'cannot be combined with Unicode'):
            prepare({'Length': 8, 'Unicode': 1, 'CodePage': 1252})
        with self.assertRaisesRegex(StringValueError, 'cannot be combined with Unicode'):
            prepare({'Length': 8, 'Unicode': True, 'CodePage': '65001'})

    def test_cp1252_round_trip_and_default_ascii_boundary(self):
        profile = prepare({'Length': 8, 'CodePage': 1252})
        self.assertEqual(parse(profile, 'Grüß').replacement, b'Gr\xfc\xdf\x00')
        current = b'Gr\xfc\xdf\x00TAI'
        self.assertTrue(desired_matches(profile, parse(profile, 'Grüß'), current))
        default = prepare({'Length': 8})
        with self.assertRaises(StringValueError):
            parse(default, 'Grüß')
        with self.assertRaises(StringValueError):
            parse(profile, 'a' * 8)

    def test_utf8_length_counts_bytes(self):
        profile = prepare({'Length': 5, 'CodePage': 65001})
        self.assertEqual(parse(profile, '🙂').replacement, '\U0001F642'.encode('utf-8') + b'\0')
        with self.assertRaises(StringValueError):
            parse(profile, '🙂a')
        with self.assertRaises(StringValueError):
            parse(profile, '🙂\0x')

    def test_unencodable_literal_refused_for_chosen_codec(self):
        with self.assertRaises(StringValueError):
            parse(prepare({'Length': 8, 'CodePage': 1252}), '🙂')
        with self.assertRaises(StringValueError):
            parse(prepare({'Length': 8, 'CodePage': 1251}), 'ß')

    def test_fixed_codepage_string_exact_units(self):
        profile = prepare({'Length': 8, 'CodePage': 1254, 'ZeroTerminate': 0})
        self.assertEqual(parse(profile, 'İstanbul').replacement, b'\xddstanbul')
        with self.assertRaises(StringValueError):
            parse(profile, 'İstanbu')
        self.assertEqual(format_value(profile, b'\xddstanbul'), 'İstanbul')

    def test_validate_round_trip_and_forgery(self):
        profile = prepare({'Length': 8, 'CodePage': 1252, 'ZeroTerminate': 1})
        validate(profile)
        forged = json.loads(json.dumps(profile))
        forged['encoding'] = 'utf-8'
        with self.assertRaises(StringValueError):
            validate(forged)
        forged2 = json.loads(json.dumps(profile))
        forged2['properties']['CodePage'] = 1250
        with self.assertRaises(StringValueError):
            validate(forged2)


class CodePageValueTypeTests(unittest.TestCase):
    def test_string_profile_dispatch_accepts_pinned_codepage(self):
        profile = prepare_value_profile('String', {'Length': 16, 'CodePage': '1251',
                                                   'ZeroTerminate': '1'})
        self.assertEqual(profile['encoding'], 'cp1251')
        self.assertEqual(profile['unit_bytes'], 1)
        self.assertEqual(profile['byte_order'], 'address')
        validate_value_profile(profile)
        raw = parse_profile_value(profile, 'Привет')
        self.assertEqual(raw, 'Привет'.encode('cp1251') + b'\0')
        self.assertEqual(format_profile_value(profile, raw + b'TAIL\0\0\0\0\0'), 'Привет')
        with self.assertRaises(ValueError):
            format_profile_value(profile, b'\x01' * 8)

    def test_unpinned_codepage_refused_through_dispatch(self):
        with self.assertRaises(ValueError):
            prepare_value_profile('String', {'Length': 8, 'CodePage': '932'})


class CodePageEngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.table = self.root / 'owned.ct'
        self.table.write_text(
            '<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
            '<CheatEntry><ID>1</ID><Description>cp1252</Description>'
            '<VariableType>String</VariableType><Length>8</Length>'
            '<CodePage>1252</CodePage><ZeroTerminate>1</ZeroTerminate>'
            '<Address>1040</Address></CheatEntry>'
            '<CheatEntry><ID>2</ID><Description>utf8</Description>'
            '<VariableType>String</VariableType><Length>16</Length>'
            '<CodePage>65001</CodePage><ZeroTerminate>1</ZeroTerminate>'
            '<Address>1080</Address></CheatEntry>'
            '<CheatEntry><ID>3</ID><Description>Unpinned</Description>'
            '<VariableType>String</VariableType><Length>8</Length>'
            '<CodePage>932</CodePage><Address>10C0</Address></CheatEntry>'
            '</CheatEntries></CheatTable>', encoding='utf-8')
        self.plan = compile_table(self.table, 'FixtureTarget.exe')
        self.memory = CpMemory()
        self.memory.data[0x40:0x48] = b'oldtail1'
        self.coordinator = DataCoordinator()
        self.engine = TrainerEngine(self.plan, state_dir=self.root / 'state',
                                    process_lock_dir=self.root / 'shared',
                                    memory_factory=lambda name: self.memory,
                                    hook_coordinator=self.coordinator)
        self.engine.poll()
        self.addCleanup(self.engine.close)

    def test_pinned_codepage_records_compile_and_unpinned_blocked(self):
        compiler_validate(self.plan)
        validate_plan(self.plan)
        entries = self.engine.entries
        self.assertTrue(entries[1]['supported'])
        self.assertEqual(entries[1]['value_profile']['encoding'], 'cp1252')
        self.assertEqual(entries[2]['value_profile']['encoding'], 'utf-8')
        self.assertFalse(entries[3]['supported'])
        self.assertIn('Codepage', entries[3]['reason'])

    def test_cp1252_write_preserves_exact_tail_and_reads_back(self):
        self.assertEqual(self.engine.set_value(1, 'Grüße'), 'Grüße')
        self.assertEqual(self.memory.read(0x1040, 8), b'Gr\xfc\xdfe\x00l1')
        self.assertEqual(self.engine.read_value(1), 'Grüße')
        self.assertEqual(self.memory.writes, [(0x1040, b'Gr\xfc\xdfe\x00')])

    def test_utf8_write_and_readback(self):
        self.assertEqual(self.engine.set_value(2, '🙂ok'), '🙂ok')
        raw = '🙂ok'.encode('utf-8') + b'\0'
        self.assertEqual(len(raw), 7)
        self.assertEqual(self.memory.read(0x1080, 16), raw + b'\0' * 9)
        self.assertEqual(self.engine.read_value(2), '🙂ok')

    def test_unencodable_literal_has_no_write_or_state_effect(self):
        with self.assertRaises(NativeRuntimeError):
            self.engine.set_value(1, '🙂')
        with self.assertRaises(NativeRuntimeError):
            self.engine.set_value(2, 'a' * 16)
        self.assertFalse(self.memory.writes)
        self.assertFalse(self.engine.blocked)
        self.assertEqual(self.memory.read(0x1040, 8), b'oldtail1')


if __name__ == '__main__':
    unittest.main()
