"""WP-48: luaCall(lua_aobscan(...)) static symbol provision into dependencies.

A supported record's statically analyzable ``luaCall`` AOB definitions
(``lua_aobscan`` / the 4-argument ``ct2trainerNthAOB``) act as ordinary
static symbol providers for the table's dependency resolution: the symbol
drops out of the record's own ``requires`` and joins its ``provides``
(casefold-sorted, deterministic), so sibling records can resolve against
it.  The plan model's named refusals leave the record on its existing
profile with the symbol unavailable, and the downstream keep-first and
provider-refusal behavior stays pinned:

- mode-section records (``{$lua}``/``{$asm}``) are outside the luacall
  plan model's domain, so no symbols merge;
- malformed ``luaCall`` syntax (unrecognized function arity) merges
  nothing;
- in-record conflicting AOB definitions (same symbol, different
  arguments) merge nothing; the record keeps ``requires`` and is blocked
  downstream by the exact named provider refusal;
- cross-record duplicate providers resolve keep-first (the first
  supported provider wins and the later duplicate stays supported
  with a runtime no-op registration, RT-4.1);
- the pinned corpus tables whose ``luaCall`` lines use non-AOB functions
  (case-05/06/07: ``speedhack_setSpeed``, ``synTick*``) derive an empty
  symbol set, so their plans stay byte-identical to the pre-WP-48
  compiler.

Self-contained synthetic tables; no CE inputs. Runtime activation of
these records still requires the injected ``luacall_binding_factory``
(gate pinned by tests/test_native_aa_luacall_wiring.py); this file pins
the plan-level provider semantics.
"""
import tempfile
import unittest
import xml.sax.saxutils
from pathlib import Path

from ct2trainer.native.aa_luacall import analyze_luacall_program
from ct2trainer.native.compiler import (compile_table,
                                        validate_plan as compiler_validate_plan)
from ct2trainer.native.engine import validate_plan


PROCESS = 'FixtureTarget.exe'

AOB_LINE = 'luaCall(lua_aobscan("anchor", "FixtureTarget.exe", "EB ?? 75"))'


def escape(script: str) -> str:
    return xml.sax.saxutils.escape(script)


def record(entry_id: int, label: str, script: str) -> str:
    return (f'<CheatEntry><ID>{entry_id}</ID><Description>{label}</Description>'
            f'<VariableType>Auto Assembler Script</VariableType>'
            f'<AssemblerScript>{escape(script)}</AssemblerScript></CheatEntry>')


def table_xml(body: str) -> str:
    return ('<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
            + body + '</CheatEntries></CheatTable>')


# Executable static envelope that references the AOB symbol, so the
# symbol lands in ``requires`` before the WP-48 merge.
PROVIDER_SCRIPT = ('[ENABLE]\n'
                   + AOB_LINE + '\n'
                   'assert(FixtureTarget.exe+40,00)\n'
                   'FixtureTarget.exe+40:\n'
                   'db 90\n'
                   'jmp anchor\n'
                   '[DISABLE]\n'
                   'FixtureTarget.exe+40:\n'
                   'db 00\n')

CONSUMER_SCRIPT = ('[ENABLE]\n'
                   'alloc(cave, 16)\n'
                   'cave:\n'
                   'jmp anchor\n'
                   '[DISABLE]\n'
                   'dealloc(cave)\n')


class LuacallSymbolProvisionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def _compile(self, body: str) -> dict:
        ct = self.root / 'table.ct'
        ct.write_text(table_xml(body), encoding='utf-8')
        return compile_table(ct, PROCESS)

    def test_luacall_aob_symbol_provides_and_drops_own_requirement(self):
        plan = self._compile(record(1, '"AOB provider"', PROVIDER_SCRIPT))
        entry = plan['entries'][0]
        self.assertTrue(entry['supported'], entry.get('reason'))
        self.assertIn('anchor', entry['provides'])
        self.assertNotIn('anchor', entry['requires'])
        compiler_validate_plan(plan)
        validate_plan(plan)

    def test_consumer_resolves_against_luacall_provider(self):
        plan = self._compile(record(1, '"AOB provider"', PROVIDER_SCRIPT)
                             + record(2, '"Consumer"', CONSUMER_SCRIPT))
        provider, consumer = plan['entries']
        self.assertTrue(provider['supported'], provider.get('reason'))
        self.assertTrue(consumer['supported'], consumer.get('reason'))
        self.assertEqual(consumer['dependency_ids'], [1])
        self.assertIn(2, plan['selected_ids'])

    def test_ct2trainer_nth_aob_four_arg_form_provides(self):
        script = ('[ENABLE]\n'
                  'luaCall(ct2trainerNthAOB("bridge", "FixtureTarget.exe", '
                  '"EB ?? 75", 2))\n'
                  'assert(FixtureTarget.exe+40,00)\n'
                  'FixtureTarget.exe+40:\n'
                  'db 90\n'
                  'jmp bridge\n'
                  '[DISABLE]\n'
                  'FixtureTarget.exe+40:\n'
                  'db 00\n')
        plan = self._compile(record(1, '"Nth AOB"', script))
        entry = plan['entries'][0]
        self.assertTrue(entry['supported'], entry.get('reason'))
        self.assertIn('bridge', entry['provides'])
        self.assertNotIn('bridge', entry['requires'])

    def test_provides_merge_is_casefold_sorted(self):
        script = ('[ENABLE]\n'
                  'luaCall(lua_aobscan("zeta", "FixtureTarget.exe", "EB ?? 75"))\n'
                  'luaCall(lua_aobscan("alpha", "FixtureTarget.exe", "90 90"))\n'
                  'assert(FixtureTarget.exe+40,00)\n'
                  'FixtureTarget.exe+40:\n'
                  'db 90\n'
                  '[DISABLE]\n'
                  'FixtureTarget.exe+40:\n'
                  'db 00\n')
        plan = self._compile(record(1, '"Two symbols"', script))
        entry = plan['entries'][0]
        self.assertTrue(entry['supported'], entry.get('reason'))
        self.assertEqual([symbol for symbol in entry['provides']
                          if symbol in ('alpha', 'zeta')], ['alpha', 'zeta'])
        self.assertNotIn('alpha', entry['requires'])
        self.assertNotIn('zeta', entry['requires'])

    def test_cross_record_keep_first_duplicate_stays_supported(self):
        # RT-4.1 (CE dupIgnore): the cross-record duplicate provider stays
        # supported behind the kept first provider; a consumer of the
        # symbol binds to the kept provider only.
        plan = self._compile(record(1, '"AOB first"', PROVIDER_SCRIPT)
                              + record(2, '"AOB second"', PROVIDER_SCRIPT)
                              + record(3, '"Consumer"', CONSUMER_SCRIPT))
        first, second, consumer = plan['entries']
        self.assertTrue(first['supported'], first.get('reason'))
        self.assertTrue(second['supported'], second.get('reason'))
        self.assertTrue(consumer['supported'], consumer.get('reason'))
        self.assertEqual(consumer['dependency_ids'], [1])

    def test_mode_section_domain_exclusion_keeps_named_refusal(self):
        script = ('[ENABLE]\n'
                  '{$lua}\n'
                  'return nil\n'
                  '{$asm}\n'
                  + AOB_LINE + '\n'
                  'assert(FixtureTarget.exe+40,00)\n'
                  'FixtureTarget.exe+40:\n'
                  'db 90\n'
                  'jmp anchor\n'
                  '[DISABLE]\n'
                  '{$lua}\n'
                  'return nil\n'
                  '{$asm}\n'
                  'FixtureTarget.exe+40:\n'
                  'db 00\n')
        plan = self._compile(record(1, '"Mode section"', script))
        entry = plan['entries'][0]
        self.assertFalse(entry['supported'])
        # RT-4.6: 'anchor' is registered nowhere in the table source (the
        # luaCall AOB form is not a static registration marker), so the
        # named refusal is the actionable per-symbol report.
        self.assertIn("Required symbol 'anchor' is not registered anywhere "
                      "in this table (referenced by 'Mode section')",
                      entry['reason'])
        # The plan model itself refuses mode sections (domain exclusion).
        with self.assertRaises(Exception) as caught:
            analyze_luacall_program(script)
        self.assertIn('AA mode sections are planned by the Lua program profile',
                      str(caught.exception))

    def test_in_record_conflict_falls_back_to_named_refusal(self):
        script = ('[ENABLE]\n'
                  'luaCall(lua_aobscan("anchor", "FixtureTarget.exe", "EB ?? 75"))\n'
                  'luaCall(lua_aobscan("anchor", "OtherModule.exe", "11 22"))\n'
                  'assert(FixtureTarget.exe+40,00)\n'
                  'FixtureTarget.exe+40:\n'
                  'db 90\n'
                  'jmp anchor\n'
                  '[DISABLE]\n'
                  'FixtureTarget.exe+40:\n'
                  'db 00\n')
        plan = self._compile(record(1, '"Conflict"', script))
        entry = plan['entries'][0]
        self.assertFalse(entry['supported'])
        # RT-4.6: the conflicting record provides no supported provider and
        # 'anchor' is registered nowhere in the table source, so the named
        # refusal is the actionable per-symbol report.
        self.assertIn("Required symbol 'anchor' is not registered anywhere "
                      "in this table (referenced by 'Conflict')",
                      entry['reason'])

    def test_malformed_luacall_falls_back_to_named_refusal(self):
        # Two arguments: not a recognizable AOB definition, so nothing merges.
        script = ('[ENABLE]\n'
                  'luaCall(lua_aobscan("anchor", "FixtureTarget.exe"))\n'
                  'assert(FixtureTarget.exe+40,00)\n'
                  'FixtureTarget.exe+40:\n'
                  'db 90\n'
                  'jmp anchor\n'
                  '[DISABLE]\n'
                  'FixtureTarget.exe+40:\n'
                  'db 00\n')
        plan = self._compile(record(1, '"Malformed"', script))
        entry = plan['entries'][0]
        self.assertFalse(entry['supported'])
        # RT-4.6: the unrecognized two-argument luaCall merges no provider
        # and 'anchor' is registered nowhere in the table source, so the
        # named refusal is the actionable per-symbol report.
        self.assertIn("Required symbol 'anchor' is not registered anywhere "
                      "in this table (referenced by 'Malformed')",
                      entry['reason'])


class PinnedCorpusStabilityTests(unittest.TestCase):
    """The pinned luaCall tables derive no AOB symbols, so plans stay stable."""

    def test_pinned_luacall_tables_carry_no_aob_symbol_merge(self):
        corpus = Path(__file__).resolve().parents[1] / 'TableReferences'
        for name in ('case-05.ct', 'case-06.ct', 'case-07.ct'):
            with self.subTest(name=name):
                plan = compile_table(str(corpus / name),
                                     'ct2synth%02d.exe' % int(name[5:7]),
                                     architecture='x64')
                compiler_validate_plan(plan)
                validate_plan(plan)
                for entry in plan['entries']:
                    if 'lua_program' in entry:
                        source = entry['lua_program']['source']
                        if 'luaCall' in source:
                            self.assertEqual(analyze_luacall_program(source).aob_symbols,
                                             (),
                                             name + ' derives AOB symbols')


if __name__ == '__main__':
    unittest.main()
