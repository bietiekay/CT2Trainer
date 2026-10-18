"""Nine literal-only contracts: owned virtual addresses, no target process."""
import copy
import hashlib
import inspect
from pathlib import Path
import sys
import unittest
from ct2trainer.native import aa as aadata
from ct2trainer.native import aa_program as aa
from ct2trainer.native.aa import AAError, compile_script
from test_native_hooks import _Memory
from iced_x86 import Decoder

def source(body,extra=''):
    return '[ENABLE]\n'+extra+'\nalloc(cave,1000)\ncave:\n'+body+'\n0x1000:\njmp cave\n[DISABLE]\n0x1000:\ndb B8 01 00 00 00\ndealloc(cave)'

class Memory(_Memory):
    def __init__(self,bits=32):
        super().__init__();self.pointer_size=bits//8;self.modules=[]
        self.data[0x10000]=bytes(0x1000)
    def module(self,name):self.modules.append(name);return 0x400000,0x1000

def link(program,memory):
    return aa.link_program(program,memory,allocations={'cave':{'address':0x10000,'size':0x1000,'executable':True,'writable':True}})

class LiteralOnlyTests(unittest.TestCase):
    def test_one_printable_ASCII_is_an_instruction_integer_without_source_rewrite(self):
        self.assertEqual(aa._operand_tokens("'R', 'A', ' ', '~'"),['0x52',',',' ','0x41',',',' ','0x20',',',' ','0x7E'])
        text=source("push 'R'\npop eax")
        profile=aa.prepare_program(text,bitness=32)
        self.assertEqual(profile['source'],text)
        self.assertEqual(profile['source_sha256'],hashlib.sha256(text.encode()).hexdigest())
        self.assertEqual(profile['requires'],[])
        self.assertIn("push 'R'",[node.get('text') for node in profile['enable']])
        aa.validate_program(profile)

    def test_bare_symbols_hexadecimal_numbers_and_registers_keep_their_meanings(self):
        self.assertEqual(aa.prepare_program(source('push R\npop eax'),bitness=32)['requires'],['R'])
        for operand,value in (("'A'",65),('A',10)):
            result=link(aa.prepare_program(source('mov eax,'+operand),bitness=32),Memory())
            raw=bytes.fromhex(next(block['bytes'] for block in result['blocks'] if block['is_allocation']))
            self.assertEqual(Decoder(32,raw,ip=0x10000).decode().immediate32,value)
        self.assertEqual(aa.prepare_program(source('mov eax,ecx'),bitness=32)['requires'],[])

    def test_named_R_label_and_registered_symbol_coexist_with_character_R(self):
        text=source("R:\npush 'R'\npop eax",'label(R)\nregistersymbol(R)')
        profile=aa.prepare_program(text,bitness=32);self.assertEqual(profile['requires'],[])
        self.assertEqual(profile['provides'],['R']);aa.validate_program(profile)
        result=link(profile,Memory())
        self.assertEqual(result['exports']['R'],0x10000)
        raw=bytes.fromhex(next(block['bytes'] for block in result['blocks'] if block['is_allocation']))
        self.assertEqual(Decoder(32,raw,ip=0x10000).decode().immediate8to32,82)

    def test_double_quoted_module_addresses_are_not_character_literals(self):
        memory=Memory();result=link(aa.prepare_program(source('mov eax,"R.exe"'),bitness=32),memory)
        raw=bytes.fromhex(next(block['bytes'] for block in result['blocks'] if block['is_allocation']))
        self.assertEqual(Decoder(32,raw,ip=0x10000).decode().immediate32,0x400000)
        self.assertIn('R.exe',memory.modules)
        with self.assertRaises(aa.AddressExpressionError):link(aa.prepare_program(source('push "R"'),bitness=32),Memory())

    def test_empty_multibyte_controls_escapes_and_unterminated_literals_refuse(self):
        bad=("''","'RR'","'é'","'\t'","'\x7f'","'\\n'","'\\'","'R", "'R'; times 100 nop")
        for value in bad:
            with self.subTest(value=value),self.assertRaises(aa.ProgramError):aa.prepare_program(source('push '+value),bitness=32)
        with self.assertRaises(aa.ProgramError):aa.prepare_program(source("push 'R\n'"),bitness=32)

    def test_character_literals_cannot_become_data_names_or_address_authority(self):
        for line in ("db 'R'","dw 'R'","dd 'R'","dq 'R'","label('R')","registersymbol('R')",
                     "define('R',1000)","define(alias,'R')","alloc('R',1000)","'R':"):
            with self.subTest(line=line),self.assertRaises(aa.ProgramError):aa.prepare_program(source(line),bitness=32)
        with self.assertRaises(aa.ProgramError):aa._expression("'R'")

    def test_quote_aware_comments_and_arg_depth_preserve_punctuation(self):
        for char in '{};/,"#%()[]$`~':
            with self.subTest(char=char):
                text=source("push '"+char+"'\npop eax")+'\n// ordinary removed comment\n'
                profile=aa.prepare_program(text,bitness=32)
                self.assertEqual(profile['source'],text)
                self.assertEqual(aa._operand_tokens("'"+char+"'"),['0x'+format(ord(char),'X')])
                result=link(profile,Memory())
                raw=bytes.fromhex(next(block['bytes'] for block in result['blocks'] if block['is_allocation']))
                self.assertEqual(Decoder(32,raw,ip=0x10000).decode().immediate8to32,ord(char))
                self.assertEqual(aa._clean_source(text).count('\n'),text.count('\n'))
        self.assertEqual(aa._args("'(', ')', '[', ']', ',', \"R'.exe\", [eax+4]"),
                         ["'('","')'","'['","']'","','",'"R\'.exe"','[eax+4]'])

    def test_canonical_source_and_exact_original_guards_still_bind_linking(self):
        profile=aa.prepare_program(source("push 'R'\npop eax",'assert(0x1000,B8 01 00 00 00)'),bitness=32)
        aa.validate_program(profile)
        for field in ('source','hash','instruction','serialized_profile'):
            forged=copy.deepcopy(profile)
            if field=='source':forged['source']=forged['source'].replace("'R'","'S'")
            elif field=='hash':forged['source_sha256']='0'*64
            elif field=='instruction':next(node for node in forged['enable'] if node.get('text')=="push 'R'")['text']="push 'S'"
            else:forged['unrelated_profile']='anything/v1'
            with self.subTest(field=field),self.assertRaises(aa.ProgramError):aa.validate_program(forged)
        memory=Memory();memory.data[0x1000]=b'\x90'*5
        with self.assertRaises(aa.ProgramError):link(profile,memory)
        self.assertFalse(memory.writes)

    def test_NASM_iced_both_architectures_decode_82_plus21_without_API_surface(self):
        self.assertEqual(set(inspect.signature(aa.prepare_program).parameters),{'source','process_name','bitness','labels','external_owned'})
        for bits,register in ((32,'eax'),(64,'rax')):
            profile=aa.prepare_program(source("push 'R'\npop "+register+'\nadd eax,#21'),bitness=bits)
            result=link(profile,Memory(bits))
            raw=bytes.fromhex(next(block['bytes'] for block in result['blocks'] if block['is_allocation']))
            instructions=list(Decoder(bits,raw,ip=0x10000))
            self.assertTrue(instructions and all(not item.is_invalid for item in instructions))
            self.assertEqual(instructions[0].immediate8to32 if bits==32 else instructions[0].immediate8to64,82)
            self.assertEqual(instructions[2].immediate8to32,21)

class DataDialectCCommentTests(unittest.TestCase):
    """WP-31: non-nested C block comments in the bounded data dialect."""

    def _base_script(self):
        # No trailing newline: _without_comments joins lines with "\n", so a
        # trailing newline in the input would shrink the line count by one.
        return ("[ENABLE]\n"
                "aobscanmodule(Anchor,owned.exe,00 11)\n"
                "assert(Anchor,11)\n"
                "Anchor:\n"
                "db 22\n"
                "[DISABLE]\n"
                "assert(Anchor,22)\n"
                "Anchor:\n"
                "db 11")

    def test_multiline_block_comment_accepted_and_line_count_preserved(self):
        script = self._base_script().replace("Anchor:\ndb 22",
                                             "/* block comment\n   spanning lines */\nAnchor:\ndb 22", 1)
        clean = aadata._without_comments(script)
        self.assertEqual(clean.count("\n"), script.count("\n"))
        result = compile_script(script)
        self.assertEqual([op["op"] for op in result["enable"]], ["scan", "assert", "write"])
        self.assertEqual(result["provides"], [])

    def test_nested_block_comment_treated_sequentially(self):
        # The first /* opens, the inner /* is content, the first */ closes;
        # the trailing db on the same line is live code.
        script = self._base_script().replace("Anchor:\ndb 22",
                                             "Anchor:\n/* a /* b */ db 33", 1) \
                                     .replace("assert(Anchor,22)", "assert(Anchor,33)")
        clean = aadata._without_comments(script)
        self.assertIn("db 33", clean)
        result = compile_script(script)
        write = next(op for op in result["enable"] if op["op"] == "write")
        self.assertEqual(write["bytes"], "33")

    def test_unmatched_block_terminator_refused(self):
        with self.assertRaisesRegex(AAError, "Unmatched C block comment terminator."):
            compile_script("[ENABLE]\n*/\n[DISABLE]\n")

    def test_unterminated_block_comment_refused(self):
        with self.assertRaisesRegex(AAError, "Unterminated C block comment."):
            compile_script("[ENABLE]\n/* a\n[DISABLE]\n")

    def test_compiler_directives_still_refused_inside_block_comment(self):
        with self.assertRaisesRegex(AAError, "Lua, C and compiler/preprocessor directives are unsupported."):
            compile_script("/* {$lua} */\n[ENABLE]\n[DISABLE]\n")


class DataDialectRegisterTests(unittest.TestCase):
    """WP-31: multi-token register directives and registerlabel."""

    def _script(self, enable_directive, disable_directive):
        return ("[ENABLE]\n"
                "define(Alpha,0x1000)\n"
                "define(Beta,0x1004)\n"
                + enable_directive + "\n"
                "[DISABLE]\n"
                + disable_directive + "\n")

    def test_multi_token_registersymbol_creates_two_register_ops(self):
        result = compile_script(self._script("registersymbol(Alpha, Beta)", "unregistersymbol(Alpha, Beta)"))
        self.assertEqual([(op["op"], op["symbol"]) for op in result["enable"] if op["op"] == "register"],
                         [("register", "Alpha"), ("register", "Beta")])
        self.assertEqual(result["provides"], ["Alpha", "Beta"])

    def test_multi_token_unregistersymbol_creates_two_unregister_ops(self):
        result = compile_script(self._script("registersymbol(Alpha,Beta)", "unregistersymbol(Alpha,Beta)"))
        self.assertEqual([(op["op"], op["symbol"]) for op in result["disable"] if op["op"] == "unregister"],
                         [("unregister", "Alpha"), ("unregister", "Beta")])

    def test_registerlabel_accepted_in_data_dialect(self):
        result = compile_script(self._script("registerlabel(Alpha, Beta)", "unregistersymbol(Alpha, Beta)"))
        self.assertEqual([(op["op"], op["symbol"]) for op in result["enable"] if op["op"] == "register"],
                         [("register", "Alpha"), ("register", "Beta")])
        self.assertEqual(result["provides"], ["Alpha", "Beta"])

    def test_single_token_registersymbol_unchanged(self):
        script = ("[ENABLE]\n"
                  "define(Alpha,0x1000)\n"
                  "registersymbol(Alpha)\n"
                  "[DISABLE]\n"
                  "unregistersymbol(Alpha)\n")
        result = compile_script(script)
        self.assertEqual([(op["op"], op["symbol"]) for op in result["enable"] if op["op"] == "register"],
                         [("register", "Alpha")])
        self.assertEqual(result["provides"], ["Alpha"])

    def test_register_symbol_wildcard_refused(self):
        # The data dialect has no scoped cleanup wildcard: validate_symbol
        # rejects the asterisk token.
        with self.assertRaisesRegex(AAError, "Symbol must contain ASCII letters, digits or underscores."):
            compile_script(self._script("registersymbol(*)", "unregistersymbol(Alpha, Beta)"))


if __name__=='__main__':unittest.main()
