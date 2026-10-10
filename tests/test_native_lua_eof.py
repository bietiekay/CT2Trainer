"""Owned regression cases for implicit Lua phase/EOF boundaries."""

import copy
import hashlib
import unittest

from ct2trainer.native.lua_program import (
    LuaProgramError, prepare_lua_program, phase_expansion, validate_lua_program,
)
from ct2trainer.native.aa_program import prepare_program, dry_link_program, ProgramError
from ct2trainer.native.assembler import AssemblyError, NasmAssembler
from ct2trainer.native.lua_host import LuaHost, LuaHostError
from ct2trainer.native.lua_bootstrap import prepare_lua_bootstrap
from test_native_assembler import Memory


def require_nasm(test):
    """Source exports can run lexical tests before restoring the pinned tool."""
    try:
        NasmAssembler()
    except AssemblyError as exc:
        test.skipTest(str(exc))


class Recorder:
    def __init__(self, result=None):
        self.calls = []
        self.checks = []
        self.result = result

    def execute(self, source, *, syntaxcheck=False):
        self.calls.append((source, syntaxcheck))
        return self.result

    def check_sources(self, sources):
        self.checks.append(sources)
        return [self.execute(source, syntaxcheck=True) for source in sources]


class EOFParserTests(unittest.TestCase):
    def test_enable_eof_closes_at_disable_without_changing_disable_aa_mode(self):
        source='[ENABLE]\n{$lua}\nreturn nil\n[DISABLE]\n// empty inverse'
        program=prepare_lua_program(source,'own.exe')
        self.assertEqual(program['static_source'],'[ENABLE]\n[DISABLE]')
        host=Recorder();phase_expansion(host,program,'enable')
        self.assertEqual(host.calls,[('return nil',False)])
        host=Recorder();phase_expansion(host,program,'disable');self.assertFalse(host.calls)

    def test_both_phases_may_open_lua_with_no_asm_closer(self):
        source='[ENABLE]\n{$lua}\non()\n[DISABLE]\n{$lua}\noff()'
        program=prepare_lua_program(source,'own.exe')
        for phase,expected in [('enable','on()'),('disable','off()')]:
            host=Recorder();phase_expansion(host,program,phase)
            self.assertEqual(host.calls,[(expected,False)])

    def test_shared_open_preamble_groups_selected_phase_and_preserves_source_hash(self):
        source='{$lua}\nlocal function helper() return 7 end\n[ENABLE]\nreturn helper()\n[DISABLE]\nreturn helper()+1'
        program=prepare_lua_program(source,'own.exe',32)
        self.assertEqual(program['source'],source)
        self.assertEqual(program['source_sha256'],hashlib.sha256(source.encode()).hexdigest())
        self.assertEqual(program['bitness'],32)
        for phase,text in [('enable','return helper()'),('disable','return helper()+1')]:
            host=Recorder();phase_expansion(host,program,phase)
            self.assertEqual(host.calls,[('local function helper() return 7 end\n'+text,False)])
        validate_lua_program(program)

    def test_inherited_mode_restatement_and_explicit_aa_exit(self):
        source='{$lua}\nlocal seed=7\n[ENABLE]\n{$lua}\nassert(seed==7)\n{$asm}\n1000:\ndb 01\n[DISABLE]\n{$lua}\nassert(seed==7)\n{$asm}\n1000:\ndb 00'
        program=prepare_lua_program(source,'own.exe')
        for phase in ['enable','disable']:
            host=Recorder();expanded=phase_expansion(host,program,phase)
            self.assertEqual(host.calls,[('local seed=7\nassert(seed==7)',False)])
            prepare_program(expanded,'own.exe')

    def test_phase_markers_in_long_strings_comments_and_escaped_quotes_are_inert(self):
        body='local a=[=[\n[DISABLE]\n{$asm}\n]=]\n--[==[\n[ENABLE]\n{$lua}\n]==]\nlocal b="first\\\n[DISABLE]\\\nlast"\nreturn nil'
        program=prepare_lua_program('[ENABLE]\n{$lua}\n'+body+'\n[DISABLE]','own.exe')
        host=Recorder();phase_expansion(host,program,'enable');self.assertEqual(host.calls,[(body,False)])

    def test_existing_explicit_chunks_keep_lua_index_continuations(self):
        body='local values={}\nlocal selected=values\n[ENABLE]\nreturn nil'
        program=prepare_lua_program('[ENABLE]\n{$lua}\n'+body+'\n{$asm}\n[DISABLE]','own.exe')
        host=Recorder();phase_expansion(host,program,'enable');self.assertEqual(host.calls,[(body,False)])

    def test_incomplete_lexical_units_malformed_phases_and_mixed_modes_fail_closed(self):
        # Missing/empty [DISABLE] with real enable content is now the accepted
        # one-shot shape; those cases moved to test_one_shot_envelopes_without_disable.
        sources=(
            '[ENABLE]\n{$lua}\nlocal v=[=[\n[DISABLE]',
            '[ENABLE]\n{$lua}\n--[=[\n[DISABLE]',
            '[ENABLE]\n{$lua}\nlocal x="bad\n[DISABLE]',
            '[ENABLE]\n{$lua}\n[ENABLE]\n[DISABLE]',
            '{$lua}\n[DISABLE]\n[ENABLE]',
            '[ENABLE]\n{$lua}\n[DISABLE]\n{$lua}\n[DISABLE]',
            '[ENABLE]\n{$lua}\n{$lua}\n[DISABLE]',
            '[ENABLE]\n{$lua} // inline\n[DISABLE]',
            '[ENABLE]\n{$lua}\n[DISABLE]\n1000:\ndb 00',
        )
        for source in sources:
            with self.subTest(source=source),self.assertRaises(LuaProgramError):prepare_lua_program(source,'own.exe')

    def test_one_shot_envelopes_without_disable_are_accepted(self):
        for source in ('[ENABLE]\n{$lua}\nreturn nil',
                       '[ENABLE]\n{$lua}\nreturn nil\n[DISABLE]\n{$asm}',
                       '[ENABLE]\n1000:\ndb 01',
                       '[ENABLE]\n1000:\ndb 01\n[DISABLE]'):
            with self.subTest(source=source):
                program=prepare_lua_program(source,'own.exe')
                self.assertTrue(program['one_shot'])
                if program['static_program'] is not None:
                    self.assertTrue(program['static_program']['one_shot'])

    def test_forged_profiles_and_returned_envelope_reentry_remain_rejected(self):
        source='[ENABLE]\n{$lua}\nreturn output\n[DISABLE]'
        program=prepare_lua_program(source,'own.exe')
        for key,value in [('source_sha256','0'*64),('provides',['fake']),('static_source','fake'),('shared',True)]:
            forged=copy.deepcopy(program);forged[key]=value
            with self.subTest(key=key),self.assertRaises(LuaProgramError):validate_lua_program(forged)
        for output in ['[DISABLE]','{$lua}\nreturn nil','luaCall(writeInteger(1000,1))',17,False,{}]:
            with self.subTest(output=output),self.assertRaises(LuaProgramError):phase_expansion(Recorder(output),program,'enable')

    def test_real_aa_return_is_still_validated_after_phase_selection(self):
        source='[ENABLE]\n{$lua}\nreturn output\n[DISABLE]\n1000:\ndb 00'
        # A static inverse without an enable site is rejected at preparation.
        with self.assertRaisesRegex(LuaProgramError,'Static AA envelope'):prepare_lua_program(source,'own.exe')
        source='[ENABLE]\n{$lua}\nreturn output\n{$asm}\n1000:\ndb 01\n[DISABLE]\n{$lua}\nreturn nil'
        # The parser can retain this enable fragment, but actual dry linking
        # refuses its absent captured inverse before an installation receipt.
        program=prepare_lua_program(source,'own.exe')
        expanded=phase_expansion(Recorder(),program,'enable')
        require_nasm(self)
        with self.assertRaisesRegex(ProgramError,'restore the captured original'):
            dry_link_program(prepare_program(expanded,'own.exe'),Memory())



class Broker:
    def __init__(self):
        self.calls = []

    def call(self, *args, **options):
        self.calls.append((args, options))
        raise AssertionError('No broker call expected')


class EOFBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.broker = Broker()
        self.host = LuaHost(self.broker)
        self.addCleanup(self.host.cancel)

    def test_shared_local_helper_and_return_execute_as_one_selected_chunk(self):
        source='{$lua}\nlocal function helper() return 7 end\n[ENABLE]\nassert(helper()==7)\nreturn "define(chosen,7)"\n[DISABLE]\nassert(helper()==7)\nreturn "define(chosen,8)"'
        program=prepare_lua_program(source,'own.exe')
        self.assertIn('[ENABLE]\ndefine(chosen,7)',phase_expansion(self.host,program,'enable'))
        self.assertIn('[DISABLE]\ndefine(chosen,8)',phase_expansion(self.host,program,'disable'))
        self.assertTrue(self.host.execute('return helper == nil'))
        self.assertFalse(self.broker.calls)

    def test_common_syntaxcheck_return_skips_entire_phase(self):
        source='{$lua}\nif syntaxcheck then return end\n[ENABLE]\nerror("must not run during check")\n[DISABLE]\nerror("must not run during check")'
        program=prepare_lua_program(source,'own.exe')
        for phase in ['enable','disable']:
            self.assertEqual(phase_expansion(self.host,program,phase,syntaxcheck=True),'[ENABLE]\n[DISABLE]')
        with self.assertRaisesRegex(LuaHostError,'must not run during check'):phase_expansion(self.host,program,'enable')
        self.assertFalse(self.broker.calls)

    def test_syntaxcheck_returns_generated_aa_but_does_not_mutate_live_globals(self):
        source='{$lua}\nlocal n=syntaxcheck and 7 or 8\n[ENABLE]\nremembered=n\nreturn "define(chosen,"..n..")"\n[DISABLE]\nerror("inactive phase")'
        program=prepare_lua_program(source,'own.exe')
        expanded=phase_expansion(self.host,program,'enable',syntaxcheck=True)
        self.assertIn('define(chosen,7)',expanded)
        self.assertTrue(self.host.execute('return remembered == nil'))
        self.assertIn('define(chosen,8)',phase_expansion(self.host,program,'enable'))
        self.assertEqual(self.host.execute('return remembered'),8)

    def test_readonly_bootstrap_replays_in_disposable_checker_and_owned_scope(self):
        profile=prepare_lua_bootstrap('function ownedHelper() return 7 end')
        self.host.install_helpers(profile['source'])
        program=prepare_lua_program('[ENABLE]\n{$lua}\nassert(ownedHelper()==7)\nreturn "define(chosen,7)"\n[DISABLE]\n{$lua}\nassert(ownedHelper()==7)','own.exe')
        self.assertIn('define(chosen,7)',phase_expansion(self.host,program,'enable',syntaxcheck=True))
        self.assertIn('define(chosen,7)',phase_expansion(self.host,program,'enable'))
        self.assertEqual(phase_expansion(self.host,program,'disable'),'[ENABLE]\n[DISABLE]')
        self.assertFalse(self.broker.calls)

    def test_open_ended_owned_long_string_and_comments_are_lua_literals(self):
        source='[ENABLE]\n{$lua}\nlocal x=[=[\n[DISABLE]\n{$asm}\n]=]\n--[==[\n[ENABLE]\n{$lua}\n]==]\nassert(x:find("[DISABLE]",1,true))\nreturn nil\n[DISABLE]'
        program=prepare_lua_program(source,'own.exe')
        self.assertEqual(phase_expansion(self.host,program,'enable'),'[ENABLE]\n[DISABLE]')

    def test_early_guard_does_not_relax_returned_aa_or_real_instruction_validation(self):
        program=prepare_lua_program('[ENABLE]\n{$lua}\nif syntaxcheck then return nil end\nreturn "luaCall(print(1))"\n[DISABLE]','own.exe')
        self.assertEqual(phase_expansion(self.host,program,'enable',syntaxcheck=True),'[ENABLE]\n[DISABLE]')
        with self.assertRaises(LuaProgramError):phase_expansion(self.host,program,'enable')
        program=prepare_lua_program('[ENABLE]\n{$lua}\nreturn "1000:\\nnot_a_real_instruction rax"\n[DISABLE]\n{$lua}\nreturn "1000:\\ndb 00"','own.exe')
        text=phase_expansion(self.host,program,'enable')
        # Parsing still delegates instructions to actual NASM at dry-link;
        # no target installation is allowed from this text alone.
        self.assertIn('not_a_real_instruction',text)
        require_nasm(self)
        with self.assertRaisesRegex(ValueError,'NASM rejected'):
            dry_link_program(prepare_program(text,'own.exe'),Memory())

    def test_eof_checker_does_not_make_caught_bootstrap_mutation_permissible(self):
        profile=prepare_lua_bootstrap('pcall(function() writeInteger(0x1000,1) end)')
        with self.assertRaises(LuaHostError):self.host.install_helpers(profile['source'])
        self.assertTrue(self.host.cancelled)
        self.assertFalse(self.broker.calls)



if __name__=='__main__':unittest.main()
