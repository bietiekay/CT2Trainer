"""Owned source exercises static envelopes and explicit Lua/AA boundaries."""

import copy
import hashlib
import unittest
from unittest.mock import patch

from ct2trainer.native.aa_program import prepare_program
from ct2trainer.native.lua_program import (LuaProgramError, MAX_SOURCE_BYTES,
                                           has_lua_sections, phase_expansion, prepare_lua_program,
                                           validate_lua_program)


STATIC = '''[ENABLE]
define(anchor,external+10)
anchor:
db 01
registersymbol(anchor)
[DISABLE]
anchor:
db 00
unregistersymbol(anchor)'''


class RecordingHost:
    def __init__(self, results=None):
        self.results = results or {}
        self.calls = []
        self.checks = []

    def execute(self, source, *, syntaxcheck=False):
        self.calls.append((source,syntaxcheck))
        return self.results.get(source)

    def check_sources(self, sources):
        self.checks.append(sources)
        return [self.execute(source,syntaxcheck=True) for source in sources]


class NativeLuaProgramTests(unittest.TestCase):
    def test_routing_ignores_inert_markers_without_validating_aa_phases(self):
        for source in ('/*\n{$lua}\n*/\nnot_an_operation', '// {$lua}\n[DISABLE]',
                       'db "{$lua}"', '"first\n{$lua}\nlast"', '{ Lua marker }'):
            with self.subTest(source=source):
                self.assertFalse(has_lua_sections(source))
        self.assertTrue(has_lua_sections('/* {$lua} */\n{$LuA}\nanything'))
        self.assertTrue(has_lua_sections('{$lua}\n--[=[\n{$asm}\n]=]'))

    def test_prepare_and_validate_never_execute_original_lua(self):
        source='{$lua}\nerror("must not run")\n{$asm}\n'+STATIC
        with patch('ct2trainer.native.lua_host.LuaHost.execute',side_effect=AssertionError('original source ran')):
            program=prepare_lua_program(source,'Owned.exe')
            validate_lua_program(program)
        self.assertEqual(program['source'],source)
        self.assertEqual(program['source_sha256'],hashlib.sha256(source.encode()).hexdigest())
        self.assertEqual(program['schema'],'ct2trainer-lua-program/v1')
        self.assertEqual(program['static_source'],STATIC)
        self.assertEqual(program['static_program'],prepare_program(STATIC,'Owned.exe'))
        self.assertEqual(program['requires'],['external'])
        self.assertEqual(program['provides'],['anchor'])

    def test_lua_call_is_pinned_and_does_not_execute_during_preparation(self):
        source='[ENABLE]\nLuaCall(error("must not run"))\n1000:\ndb 01\n[DISABLE]\nLUACALL(undo())\n1000:\ndb 00'
        with patch('ct2trainer.native.lua_host.LuaHost.execute',side_effect=AssertionError('conversion executed Lua')):
            program=prepare_lua_program(source,'owned.exe')
            validate_lua_program(program)
        self.assertTrue(has_lua_sections(source))
        self.assertEqual(program['source'],source)
        self.assertEqual(program['source_sha256'],hashlib.sha256(source.encode()).hexdigest())
        self.assertNotIn('Call',program['static_source'])
        self.assertEqual(program['requires'],[])
        self.assertEqual(program['provides'],[])

    def test_lua_call_phases_preamble_and_sections_use_one_owned_host(self):
        source='luaCall(function helper() return 7 end)\n[ENABLE]\nluaCall(enable(helper()))\n{$lua}\nexplicit()\n{$asm}\n1000:\ndb 01\n[DISABLE]\nluaCall(disable(helper()))\n1000:\ndb 00'
        program=prepare_lua_program(source,'owned.exe')
        host=RecordingHost({'enable(helper())':'define(enabled,1)','disable(helper())':'define(disabled,1)'})
        enabled=phase_expansion(host,program,'enable')
        self.assertEqual(host.calls,[('function helper() return 7 end',False),('enable(helper())',False),('explicit()',False)])
        self.assertIn('define(enabled,1)',enabled)
        self.assertNotIn('define(disabled,1)',enabled)
        host.calls.clear()
        disabled=phase_expansion(host,program,'disable')
        self.assertEqual(host.calls,[('function helper() return 7 end',False),('disable(helper())',False)])
        self.assertIn('define(disabled,1)',disabled)
        host.calls.clear()
        phase_expansion(host,program,'enable',syntaxcheck=True)
        self.assertEqual(host.checks,[['function helper() return 7 end','enable(helper())','explicit()']])
        self.assertTrue(all(syntaxcheck for _,syntaxcheck in host.calls))

    def test_lua_call_lexing_preserves_lua_strings_tables_comments_and_nested_calls(self):
        bodies=(
            'record("a ) // /* { {$asm}", nested(1,(2+3)))',
            "record('a ) // /* {', {value=')'})",
            'record([==[) -- {$lua} [DISABLE]]==])',
            'record(1 --[=[ ) {$asm} ]=] ,2)',
            'local value="escaped \\\" )"; record(value)',
        )
        for body in bodies:
            with self.subTest(body=body):
                source='[ENABLE]\n/* leading */ luaCall('+body+') /* trailing\n{$lua}\n[DISABLE]\n*/\n[DISABLE]'
                program=prepare_lua_program(source,'owned.exe')
                host=RecordingHost()
                self.assertEqual(phase_expansion(host,program,'enable'),'[ENABLE]\n[DISABLE]')
                self.assertEqual(host.calls,[(body,False)])

    def test_lua_call_inert_markers_do_not_route_or_execute(self):
        for source in ('// luaCall(error("bad"))','/*\nluaCall(error("bad"))\n*/',
                       'db "luaCall(error())"','"first\nluaCall(error())\nlast"',
                       '{luaCall(error("bad"))}', 'luaCall.handler:', 'luaCall$local:',
                       'luaCall:', 'luaCallback:'):
            with self.subTest(source=source):
                self.assertFalse(has_lua_sections(source))
        program=prepare_lua_program('/* luaCall(bad()) */\n'+STATIC,'owned.exe')
        host=RecordingHost()
        self.assertEqual(phase_expansion(host,program,'enable'),STATIC)
        self.assertFalse(host.calls)

    def test_lua_call_wrapper_rejects_injection_unclosed_input_and_bounds(self):
        bodies=('luaCall()','luaCall','luaCall doWork()',
                'luaCall(doWork()) 1000: db 01','luaCall(doWork()) [DISABLE]',
                'luaCall(doWork()) {$lua}','luaCall(doWork()) luaCall(other())',
                'luaCall(doWork()','luaCall("not closed)',
                'luaCall([[not closed))','luaCall(doWork() -- hidden wrapper)',
                'luaCall(doWork()) -- outside comment',
                'luaCall('+('('*65)+'1'+(')'*65)+')')
        for body in bodies:
            with self.subTest(body=body),self.assertRaises(LuaProgramError):
                prepare_lua_program('[ENABLE]\n'+body+'\n[DISABLE]','owned.exe')
        with self.assertRaises(LuaProgramError):
            prepare_lua_program('[ENABLE]\n'+('luaCall(return nil)\n'*65)+'[DISABLE]','owned.exe')
        with self.assertRaises(LuaProgramError):
            prepare_lua_program('[ENABLE]\n'+('luaCall(return nil)\n'*64)+'{$lua}\nreturn nil\n{$asm}\n[DISABLE]','owned.exe')

    def test_lua_call_returned_text_cannot_reenter_lua_or_escape_phases(self):
        program=prepare_lua_program('[ENABLE]\nluaCall(return output)\n[DISABLE]','owned.exe')
        for value in ('luaCall(writeBytes(0x1000,1))','/* comment */ luaCall(writeBytes(0x1000,1))',
                      '[DISABLE]','{$lua}\nwriteBytes(0x1000,1)\n{$asm}'):
            with self.subTest(value=value),self.assertRaises(LuaProgramError):
                phase_expansion(RecordingHost({'return output':value}),program,'enable')
        self.assertIn('// luaCall(inert)',phase_expansion(RecordingHost({'return output':'// luaCall(inert)'}),program,'enable'))

    def test_lua_call_real_lua_context_and_quoted_data_are_preserved(self):
        try:
            import lupa.lua53
        except ImportError:
            self.skipTest('pinned MIT Lupa Lua53 dependency is not installed')
        from ct2trainer.native.lua_host import LuaHost
        class Broker:
            def call(self,*args,**options):raise AssertionError('No broker request expected')
        host=LuaHost(Broker())
        self.addCleanup(host.cancel)
        source='luaCall(function helper(x) return x end)\n[ENABLE]\nluaCall(local t={value=\') // /* { {$asm}\'}; assert(helper(t.value)==t.value); return "define(good,7)")\n1000:\ndb 01\n[DISABLE]\nluaCall(error("inactive phase must not run"))\n1000:\ndb 00'
        program=prepare_lua_program(source,'owned.exe')
        self.assertIn('define(good,7)',phase_expansion(host,program,'enable'))
        self.assertEqual(host.execute('return helper(9)'),9)
        self.assertIn('define(good,7)',phase_expansion(host,program,'enable',syntaxcheck=True))

    def test_canonical_static_source_handles_crlf_and_aa_comments(self):
        source='/*\n{$lua}\n[DISABLE]\n*/\n{ [DISABLE] }\n/* {$asm} */\n'+STATIC.replace('[ENABLE]','[enable] // phase').replace('db 01','db /* inert */ 01')
        source=source.replace('\n','\r\n')
        program=prepare_lua_program(source,'Owned.exe',32)
        self.assertEqual(program['source'],source)
        self.assertEqual(program['bitness'],32)
        self.assertNotIn('inert',program['static_source'])
        self.assertTrue(program['static_source'].startswith('[ENABLE]\n'))
        self.assertNotIn('\r',program['static_source'])
        validate_lua_program(program)

    def test_lua_only_envelope_has_no_claimed_runtime_symbols(self):
        source='// before\n{$lua}\nsetup()\n{$asm}\n[ENABLE]\n{$lua}\nreturn "registersymbol(dynamic)"\n{$asm}\n[DISABLE]\n{$lua}\nundo()\n{$asm}\n/* after */'
        program=prepare_lua_program(source,'owned.exe')
        self.assertEqual(program['static_source'],'[ENABLE]\n[DISABLE]')
        self.assertIsNone(program['static_program'])
        self.assertEqual(program['requires'],[])
        self.assertEqual(program['provides'],[])
        validate_lua_program(program)

    def test_nonempty_static_fragment_still_requires_valid_aa_program(self):
        for source in ('[ENABLE]\nalloc(cave,1000)\n[DISABLE]\ndealloc(cave)',
                       '[ENABLE]\n{$lua}\nreturn "1000: db 01"\n{$asm}\n[DISABLE]\n1000:\ndb 00'):
            with self.subTest(source=source),self.assertRaisesRegex(LuaProgramError,'Static AA envelope'):
                prepare_lua_program(source,'owned.exe')

    def test_forged_metadata_and_unknown_fields_are_reconstructed(self):
        original=prepare_lua_program('{$lua}\nreturn nil\n{$asm}\n'+STATIC,'owned.exe')
        changes={
            'source_sha256':'0'*64,'requires':['forged'],'provides':['forged'],
            'static_source':'[ENABLE]\n[DISABLE]','static_program':None,
            'unexpected':True,'bitness':True,'process_name':'other.exe',
        }
        for key,value in changes.items():
            with self.subTest(key=key):
                changed=copy.deepcopy(original);changed[key]=value
                with self.assertRaises(LuaProgramError):validate_lua_program(changed)
        changed=copy.deepcopy(original)
        changed['static_program']['enable'][0]['expression']='forged'
        with self.assertRaises(LuaProgramError):validate_lua_program(changed)
        changed=copy.deepcopy(original);changed['provides']=float('nan')
        with self.assertRaises(LuaProgramError):validate_lua_program(changed)

    def test_invalid_phase_and_language_envelopes_fail_statically(self):
        # WP-26 note: '[ENABLE]\n{$asm}\n[DISABLE]' is no longer invalid -
        # the redundant {$asm} is a CE no-op, making the envelope identical
        # to the already-accepted empty '[ENABLE]\n[DISABLE]' program.
        bad_sources=(
            '[DISABLE]\n[ENABLE]', '[ENABLE]', '[ENABLE]\n[DISABLE]\n[ENABLE]',
            '[ENABLE]\n[enable]\n[DISABLE]',
            '[ENABLE]\n{$lua}\n{$lua}\n{$asm}\n[DISABLE]',
            '[ENABLE]\n{$lua} // inline\n{$asm}\n[DISABLE]',
            '[ENABLE]\n{$c}\n[DISABLE]', '[ENABLE]\n/*\n[DISABLE]',
            '[ENABLE]\n{$lua}\nlocal x="bad\n{$asm}\n[DISABLE]',
            '[ENABLE]\n{$lua}\n--[=[\n{$asm}\n[DISABLE]',
        )
        for source in bad_sources:
            with self.subTest(source=source),self.assertRaises(LuaProgramError):
                prepare_lua_program(source,'owned.exe')

    def test_source_target_and_chunk_bounds(self):
        for target in (None,'game',' game.exe','C:\\game.exe','game.exe\n','.EXE'):
            with self.subTest(target=target),self.assertRaises(LuaProgramError):
                prepare_lua_program(STATIC,target)
        for bitness in (True,16,None):
            with self.subTest(bitness=bitness),self.assertRaises(LuaProgramError):
                prepare_lua_program(STATIC,'owned.exe',bitness)
        for source in ('x'*(MAX_SOURCE_BYTES+1), '[ENABLE]\n'+('{$lua}\n{$asm}\n'*65)+'[DISABLE]',
                       '[ENABLE]\n'+'\n'*65536+'[DISABLE]', '\ud800'):
            with self.subTest(size=len(source)),self.assertRaises(LuaProgramError):
                prepare_lua_program(source,'owned.exe')

    def test_phase_selection_replays_preamble_and_keeps_both_static_phases(self):
        source='{$lua}\npreamble()\n{$asm}\n[ENABLE]\n{$lua}\nenable()\n{$asm}\n1000:\ndb 01\n[DISABLE]\n{$lua}\ndisable()\n{$asm}\n1000:\ndb 00'
        program=prepare_lua_program(source,'owned.exe')
        host=RecordingHost({'preamble()':'define(seed,1)','enable()':'define(enabled,1)','disable()':'define(disabled,1)'})
        enabled=phase_expansion(host,program,'enable')
        self.assertEqual([source for source,_ in host.calls],['preamble()','enable()'])
        self.assertIn('define(enabled,1)',enabled);self.assertNotIn('define(disabled,1)',enabled)
        self.assertTrue(enabled.startswith('define(seed,1)\n[ENABLE]'))
        self.assertIn('[DISABLE]\n1000:\ndb 00',enabled)
        host.calls.clear()
        disabled=phase_expansion(host,program,'disable')
        self.assertEqual([source for source,_ in host.calls],['preamble()','disable()'])
        self.assertIn('[ENABLE]\n1000:\ndb 01',disabled)
        self.assertIn('define(disabled,1)',disabled);self.assertNotIn('define(enabled,1)',disabled)

    def test_long_strings_comments_and_short_string_continuations_shield_markers(self):
        chunks=(
            'local value=[==[\n{$asm}\n[DISABLE]\n]==]\nreturn nil',
            '--[=[\n{$asm}\n[ENABLE]\n]=]\nreturn nil',
            'local value="first\\\n{$asm}\\\n[DISABLE]\\\nlast"\nreturn nil',
            'local value="\\z\n  {$asm}\\\nlast"\nreturn nil',
            'local value="{$asm}"; local other=\'--[=[\'; -- {$asm}\nreturn nil',
            'local values={}\nlocal selected=values\n[ENABLE]\nreturn nil',
        )
        for body in chunks:
            with self.subTest(body=body):
                source='[ENABLE]\n{$lua}\n'+body+'\n{$asm}\n1000:\ndb 01\n[DISABLE]\n1000:\ndb 00'
                program=prepare_lua_program(source,'owned.exe')
                host=RecordingHost()
                expanded=phase_expansion(host,program,'enable')
                self.assertEqual(host.calls,[(body,False)])
                self.assertEqual(expanded,program['static_source'])

    def test_invalid_returns_and_added_phases_are_rejected(self):
        program=prepare_lua_program('[ENABLE]\n{$lua}\nbody()\n{$asm}\n[DISABLE]','owned.exe')
        for value in (False,17,{},[],('db 01',None),'[ENABLE]\n1000:\ndb 01',
                      '[DISABLE] // added','{$lua}\nreturn nil\n{$asm}','/* unterminated'):
            with self.subTest(value=value),self.assertRaises(LuaProgramError):
                phase_expansion(RecordingHost({'body()':value}),program,'enable')
        self.assertEqual(phase_expansion(RecordingHost(),program,'enable'),'[ENABLE]\n[DISABLE]')
        inert='/*\n[DISABLE]\n*/\n1000:\ndb "[ENABLE]"'
        self.assertIn(inert,phase_expansion(RecordingHost({'body()':inert}),program,'enable'))

    def test_expansion_validation_and_size_bound_precede_untrusted_output(self):
        source='[ENABLE]\n{$lua}\none()\n{$asm}\n{$lua}\ntwo()\n{$asm}\n[DISABLE]'
        program=prepare_lua_program(source,'owned.exe')
        host=RecordingHost({'one()':'//'+('a'*600000),'two()':'//'+('b'*600000)})
        with self.assertRaisesRegex(LuaProgramError,'Expanded AA'):
            phase_expansion(host,program,'enable')
        for phase in ('ENABLE','other',[],None):
            with self.subTest(phase=phase),self.assertRaises(LuaProgramError):
                phase_expansion(RecordingHost(),program,phase)
        changed=copy.deepcopy(program);changed['source_sha256']='0'*64
        host=RecordingHost()
        with self.assertRaises(LuaProgramError):phase_expansion(host,changed,'enable')
        self.assertFalse(host.calls)

    def test_syntaxcheck_shares_preamble_in_one_disposable_lua_state(self):
        try:
            import lupa.lua53
        except ImportError:
            self.skipTest('pinned MIT Lupa Lua53 dependency is not installed')
        from ct2trainer.native.lua_host import LuaHost,LuaMemoryPool
        class Broker:
            def call(self,*args,**options):raise AssertionError('No broker request expected')
        source='{$lua}\nfunction helper() return 7 end\n{$asm}\n[ENABLE]\n{$lua}\nreturn "define(value,"..helper()..")"\n{$asm}\n1000:\ndb 01\n[DISABLE]\n{$lua}\nerror("inactive phase")\n{$asm}\n1000:\ndb 00'
        program=prepare_lua_program(source,'owned.exe')
        host=LuaHost(Broker(),memory_pool=LuaMemoryPool())
        host.execute('function helper() return 99 end')
        expanded=phase_expansion(host,program,'enable',syntaxcheck=True)
        self.assertIn('define(value,7)',expanded)
        self.assertEqual(host.execute('return helper()'),99)
        prepare_program(expanded,'owned.exe')
        host.cancel()

    def test_owned_lua_marker_literals_execute_as_single_chunks(self):
        try:
            import lupa.lua53
        except ImportError:
            self.skipTest('pinned MIT Lupa Lua53 dependency is not installed')
        from ct2trainer.native.lua_host import LuaHost
        class Broker:
            def call(self,*args,**options):raise AssertionError('No broker request expected')
        bodies=(
            'local value=[==[\n{$asm}\n[DISABLE]\n]==]\nassert(value:find("[DISABLE]",1,true)); return nil',
            '--[=[\n{$asm}\n[ENABLE]\n]=]\nreturn nil',
            'local value="first\\\n{$asm}\\\n[DISABLE]\\\nlast"\nassert(value:find("{$asm}",1,true)); return nil',
            'local value="\\z\n  {$asm}\\\nlast"\nassert(value:find("{$asm}",1,true)); return nil',
            'local values={}\nlocal selected=values\n[ENABLE]\nreturn nil',
        )
        host=LuaHost(Broker())
        for body in bodies:
            with self.subTest(body=body):
                source='[ENABLE]\n{$lua}\n'+body+'\n{$asm}\n1000:\ndb 01\n[DISABLE]\n1000:\ndb 00'
                program=prepare_lua_program(source,'owned.exe')
                self.assertEqual(phase_expansion(host,program,'enable'),program['static_source'])
        host.cancel()


class NativeNthProgramTests(unittest.TestCase):
    CALL = 'ct2trainerNthAOB("scanOwned","owned.exe","11 ??",2)'
    SOURCE = '[ENABLE]\nluaCall(' + CALL + ')\ndefine(provider,external+10)\nregistersymbol(provider)\nscanOwned:\ndb 01\n[DISABLE]\nscanOwned:\ndb 11\nunregistersymbol(provider)'

    def test_dependencies_retain_static_source_and_partition_only_proven_local_scans(self):
        program = prepare_lua_program(self.SOURCE, 'owned.exe')
        self.assertEqual(program['static_program']['requires'], ['external', 'scanOwned'])
        self.assertEqual(program['requires'], ['external'])
        self.assertEqual(program['provides'], ['provider', 'scanOwned'])
        self.assertEqual(program['source'], self.SOURCE)
        self.assertEqual(program['source_sha256'], hashlib.sha256(self.SOURCE.encode()).hexdigest())
        self.assertEqual(program['dynamic_definitions'][0]['occurrence'], 2)
        self.assertNotIn('nth_aob_helper', program)
        validate_lua_program(program)

    def test_unknown_same_named_table_helper_keeps_its_external_dependencies(self):
        program = prepare_lua_program(self.SOURCE.replace('ct2trainerNthAOB', 'lua_aobscan'), 'owned.exe')
        self.assertEqual(program['requires'], ['external', 'scanOwned'])
        self.assertEqual(program['provides'], ['provider'])
        self.assertNotIn('dynamic_definitions', program)

    def test_only_complete_literal_enable_calls_receive_source_adapter_semantics(self):
        invalid = ('ct2trainerNthAOB("scanOwned","owned.exe","11 ??",0)',
                   'ct2trainerNthAOB("scanOwned","owned.exe","11 ??",65537)',
                   'ct2trainerNthAOB("scanOwned","owned.exe","11 ??",1+1)',
                   'ct2trainerNthAOB("scanOwned","owned.exe","11 ??",0x2)',
                   'ct2trainerNthAOB("scanOwned","","11 ??",2)',
                   'ct2trainerNthAOB("scanOwned","owned.exe","?? ??",2)',
                   self.CALL + '; writeInteger(0x1000,7)',
                   'ct2trainerNthAOB(name,"owned.exe","11 ??",2)',
                   'ct2trainerNthAOB("scan\\x4fwned","owned.exe","11 ??",2)')
        for call in invalid:
            with self.subTest(call=call), self.assertRaises(LuaProgramError):
                prepare_lua_program(self.SOURCE.replace(self.CALL, call), 'owned.exe')
        for source in ('luaCall(' + self.CALL + ')\n[ENABLE]\n[DISABLE]',
                       '[ENABLE]\n[DISABLE]\nluaCall(' + self.CALL + ')'):
            with self.subTest(source=source), self.assertRaisesRegex(LuaProgramError, 'restricted to ENABLE'):
                prepare_lua_program(source, 'owned.exe')

    def test_scan_symbols_cannot_collide_with_static_locals_or_case_variants(self):
        for inserted in ('define(scanOwned,1000)', 'label(scanOwned)',
                         'alloc(scanOwned,100)', 'aobscanmodule(scanOwned,owned.exe,11 22)',
                         'luaCall(' + self.CALL.replace('scanOwned', 'SCANOWNED') + ')'):
            source = self.SOURCE.replace('define(provider', inserted + '\ndefine(provider')
            with self.subTest(inserted=inserted), self.assertRaisesRegex(LuaProgramError, 'collides|more than once'):
                prepare_lua_program(source, 'owned.exe')

    def test_serialized_scans_cannot_forge_metadata_or_drop_a_real_dependency(self):
        original = prepare_lua_program(self.SOURCE, 'owned.exe')
        for change in (lambda program: program.update(requires=[]),
                       lambda program: program.update(provides=['provider']),
                       lambda program: program['dynamic_definitions'][0].update(occurrence=3),
                       lambda program: program['dynamic_definitions'][0].update(part_index=0),
                       lambda program: program['dynamic_definitions'][0].update(module='foreign.exe'),
                       lambda program: program.update(nth_aob_helper={'schema': 'forged'})):
            program = copy.deepcopy(original); change(program)
            with self.subTest(change=change), self.assertRaises(LuaProgramError):
                validate_lua_program(program)

    def test_expansion_requires_owned_resolver_and_never_executes_the_scan_call_as_lua(self):
        source = self.SOURCE.replace('define(provider', 'luaCall(ordinary())\ndefine(provider')
        program = prepare_lua_program(source, 'owned.exe')
        host = RecordingHost()
        with self.assertRaisesRegex(LuaProgramError, 'owned read/scan resolver'):
            phase_expansion(host, program, 'enable')
        self.assertFalse(host.calls)
        scans = []
        def resolve(definition, checking):
            scans.append((definition, checking))
        self.assertEqual(phase_expansion(host, program, 'enable', nth_resolver=resolve), program['static_source'])
        self.assertEqual(host.calls, [('ordinary()', False)])
        self.assertFalse(scans[0][1])
        host = RecordingHost(); scans.clear()
        phase_expansion(host, program, 'enable', syntaxcheck=True, nth_resolver=resolve)
        self.assertTrue(scans[0][1])
        self.assertEqual(host.checks, [['ordinary()']])
        scans.clear()
        phase_expansion(host, program, 'disable', nth_resolver=resolve)
        self.assertFalse(scans)
        with self.assertRaisesRegex(LuaProgramError, 'arbitrary AA text'):
            phase_expansion(RecordingHost(), program, 'enable', nth_resolver=lambda *args: 'dd 7')


if __name__=='__main__':
    unittest.main()
