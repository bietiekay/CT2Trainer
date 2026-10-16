"""Owned scripts and fake memory exercise the independently implemented linker."""

from __future__ import annotations

import copy
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from ct2trainer.native.aa_program import ProgramError, dry_link_program, link_program, prepare_program, preflight_program, validate_program
from ct2trainer.native.address_expression import AddressExpressionError, expression_symbols, integer, resolve_expression
import ct2trainer.native.assembler as assembler
from ct2trainer.native.assembler import AssemblyError, NasmAssembler, find_nasm


class Memory:
    def __init__(self):
        self.data = {}
        self.reads = []
        self.scans = []

    def read(self, address, size):
        self.reads.append((address, size))
        return bytes(self.data.get(address + index, 0) for index in range(size))

    def module(self, name):
        if name.casefold() != "owned.exe":
            raise ValueError("Unknown owned module")
        return 0x140000000, 0x100000

    def scan_module(self, module, pattern):
        self.scans.append((module, pattern))
        return 0x140001000

    def seed(self, address, data):
        self.data.update({address + index: byte for index, byte in enumerate(data)})


OWNED_HOOK = """[ENABLE]
aobscanmodule(anchor,owned.exe,89 5F 44 48 8B 5C 24 30)
alloc(cave,$1000,anchor)
label(code,resume)
cave:
code:
 add ebx,#1
 mov [rdi+44],ebx
 mov rbx,[rsp+30]
 jmp resume
anchor:
 jmp cave
 nop 3
resume:
registersymbol(anchor,code)
[DISABLE]
anchor:
 db 89 5F 44 48 8B 5C 24 30
unregistersymbol(*)
dealloc(*)
"""


class ExpressionTests(unittest.TestCase):
    def test_hex_math_parent_and_pointer(self):
        memory = Memory()
        memory.seed(0x1100, (0x2200).to_bytes(8, "little"))
        self.assertEqual(integer("1024"), 0x1024)
        self.assertEqual(integer("#1024"), 1024)
        self.assertEqual(resolve_expression("[root+100]+4*2", memory, {"root": 0x1000}), 0x2208)
        self.assertEqual(resolve_expression("+10", memory, parent=0x1000), 0x1010)
        self.assertEqual(resolve_expression('"owned.exe"+20', memory), 0x140000020)
        self.assertEqual(resolve_expression("$process+20", memory, process_name="owned.exe"), 0x140000020)
        self.assertEqual(expression_symbols("[Root+10]+Other*2"), ["Root", "Other"])

    def test_expression_bounds(self):
        memory = Memory()
        for text in ("__import__('os')", "x;write()", "1/0", "FFFFFFFFFFFFFFFF+1", "[" * 40 + "1" + "]" * 40):
            with self.subTest(text=text), self.assertRaises(AddressExpressionError):
                resolve_expression(text, memory)
        with self.assertRaises(AddressExpressionError):
            resolve_expression("Root", memory, {"Root": 1, "root": 2})

    def test_remote_exports_preserve_exe_and_dll_suffixes(self):
        class Exports:
            def __init__(self):
                self.requests = []

            def resolve_export(self, module, symbol):
                self.requests.append((module, symbol))
                return 0x1000

        memory = Exports()
        for expression in ('NativeHookFixture.exe.fixture_result', 'Kernel32.dll.GetTickCount64', 'user32.GetAsyncKeyState'):
            self.assertEqual(resolve_expression(expression, memory), 0x1000)
            self.assertEqual(expression_symbols(expression), [])
        self.assertEqual(memory.requests, [('NativeHookFixture.exe', 'fixture_result'), ('Kernel32.dll', 'GetTickCount64'), ('user32.dll', 'GetAsyncKeyState')])


class ProgramTests(unittest.TestCase):
    def test_metadata_and_scoped_cleanup(self):
        program = prepare_program(OWNED_HOOK, "owned.exe")
        self.assertEqual(program["requires"], [])
        self.assertEqual(program["provides"], ["anchor", "code"])
        self.assertEqual(program["allocations"], ["cave"])
        self.assertEqual(program["disable"][-2]["symbols"], ["anchor", "code"])
        self.assertEqual(program["disable"][-1]["symbols"], ["cave"])
        validate_program(program)

    def test_preflight_is_read_only_and_handles_scan_redefinition(self):
        source = OWNED_HOOK.replace("alloc(cave", "define(anchor,anchor+D)\nalloc(cave")
        memory = Memory()
        result = preflight_program(prepare_program(source), memory)
        self.assertEqual(result["symbols"]["anchor"], 0x14000100D)
        self.assertEqual(result["allocation_requests"], [{"name": "cave", "size": 4096, "near": 0x14000100D, "executable": True, "writable": False}])

    def test_dependency_symbols(self):
        source = "[ENABLE]\nexternal+10:\n mov eax,[external]\n[DISABLE]\nexternal+10:\n db 90"
        self.assertEqual(prepare_program(source)["requires"], ["external"])

    def test_invalid_directives_and_injection_rejected(self):
        for line in ("%include evil", "incbin evil", "section evil", "times 4 db 90", "mov eax,`touch`", "createthread(code)", "{$lua}\nreturn 1", "db 90; incbin evil", "alloc(x,FFFFFFFF)"):
            with self.subTest(line=line), self.assertRaises(ProgramError):
                prepare_program("[ENABLE]\n1000:\n" + line + "\n[DISABLE]\n1000:\n db 90")

    def test_cleanup_cannot_remove_foreign_resources(self):
        with self.assertRaisesRegex(ProgramError, "owned"):
            prepare_program(OWNED_HOOK.replace("dealloc(*)", "dealloc(foreign)"))

    def test_ir_mutation_rejected(self):
        program = prepare_program(OWNED_HOOK)
        changed = copy.deepcopy(program)
        changed["enable"][0]["module"] = "foreign.exe"
        with self.assertRaises(ProgramError):
            validate_program(changed)
        one = prepare_program('[ENABLE]\nalloc(cave,1)\ncave:\nnop\n[DISABLE]\ndealloc(*)')
        one['enable'][0]['size'] = True
        with self.assertRaises(ProgramError):
            validate_program(one)

    def test_generated_byte_bound(self):
        source = "[ENABLE]\n1000:\n" + "nop 10000\n" * 65 + "[DISABLE]\n1000:\n db 90"
        with self.assertRaisesRegex(ProgramError, "generated-byte"):
            prepare_program(source)

    def test_unbound_anonymous_labels_rejected_during_prepare(self):
        for operand in ("@f", "@b"):
            with self.subTest(operand=operand), self.assertRaisesRegex(ProgramError, "no target"):
                prepare_program('[ENABLE]\n1000:\njmp ' + operand + '\n[DISABLE]\n1000:\ndb 90')

    def test_c_comment_directives_are_inert(self):
        source = "/* [ENABLE]\n%include bad */\n" + OWNED_HOOK
        self.assertEqual(prepare_program(source)["provides"], ["anchor", "code"])
        with self.assertRaisesRegex(ProgramError, "Unterminated"):
            prepare_program(OWNED_HOOK + "\n/*")

    def test_assert_wildcards_capture_actual_bytes(self):
        source = OWNED_HOOK.replace("alloc(cave", "assert(anchor,8? 5F ??)\nalloc(cave")
        memory = Memory()
        memory.seed(0x140001000, bytes.fromhex("89 5F 44"))
        result = preflight_program(prepare_program(source), memory)
        self.assertEqual(result["guards"], [{"address": 0x140001000, "bytes": "895F44"}])
        memory.seed(0x140001000, b"\x90")
        with self.assertRaisesRegex(ProgramError, "Assertion"):
            preflight_program(prepare_program(source), memory)


class RealNasmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.assembler = NasmAssembler()
        except AssemblyError as exc:
            raise unittest.SkipTest(str(exc))

    def test_remote_multisection_hook_and_restore(self):
        program = prepare_program(OWNED_HOOK)
        memory = Memory()
        original = bytes.fromhex("89 5F 44 48 8B 5C 24 30")
        memory.seed(0x140001000, original)
        allocations = {"cave": {"address": 0x140002000, "size": 4096, "executable": True}}
        linked = link_program(program, memory, allocations=allocations, assembler=self.assembler)
        self.assertEqual(len(linked["blocks"]), 2)
        cave, patch = linked["blocks"]
        self.assertEqual(bytes.fromhex(cave["bytes"])[:10], bytes.fromhex("83 C3 01 89 5F 44 48 8B 5C 24"))
        self.assertEqual(bytes.fromhex(patch["bytes"]), bytes.fromhex("E9 FB 0F 00 00 90 90 90"))
        self.assertEqual(patch["original"], original.hex().upper())
        self.assertTrue(cave["is_allocation"])
        self.assertTrue(patch["requires_coordinator"])
        self.assertEqual(linked["exports"]["code"], 0x140002000)
        restored = link_program(program, memory, symbols=linked["symbols"], allocations=allocations, phase="disable", assembler=self.assembler)
        self.assertEqual(restored["blocks"][0]["bytes"], original.hex().upper())

    def test_anonymous_avx_float_and_remote_alignment(self):
        source = """[ENABLE]
alloc(cave,1000)
label(flag,ending)
cave:
flag:
 db 0
 align 10 CC
 cmp byte ptr [flag],1
 je @f
 mov [rax],(float)1.0
 vmovss xmm0,[rcx+0C]
@@:
 vxorps xmm1,xmm1,xmm1
ending:
 dq (double)999
registersymbol(flag,ending)
[DISABLE]
unregistersymbol(*)
dealloc(*)
"""
        memory = Memory()
        result = link_program(prepare_program(source), memory, allocations={"cave": {"address": 0x140002003, "size": 4096}}, assembler=self.assembler)
        data = bytes.fromhex(result["blocks"][0]["bytes"])
        self.assertEqual(data[:13], b"\x00" + b"\xCC" * 12)
        self.assertIn(bytes.fromhex("C5 FA 10 41 0C"), data)
        self.assertIn(bytes.fromhex("00 00 80 3F"), data)

    def test_readmem_and_data_only_allocation(self):
        source = "[ENABLE]\nalloc(saved,100)\nlabel(orig)\nsaved:\norig:\nreadmem(anchor,8)\nregistersymbol(orig)\n[DISABLE]\nanchor:\nreadmem(orig,8)\nunregistersymbol(*)\ndealloc(*)"
        memory = Memory()
        memory.seed(0x2000, b"owned123")
        program = prepare_program(source)
        result = link_program(program, memory, {"anchor": 0x2000}, {"saved": {"address": 0x3000, "size": 256}}, assembler=self.assembler)
        self.assertEqual(result["blocks"][0]["bytes"], b"owned123".hex().upper())
        self.assertTrue(result["blocks"][0]["executable"])
        self.assertTrue(result["requires_coordinator"])
        memory.seed(0x3000, bytes.fromhex(result["blocks"][0]["bytes"]))
        restored = link_program(program, memory, result["symbols"], {"saved": {"address": 0x3000, "size": 256}}, phase="disable", assembler=self.assembler)
        self.assertEqual(restored["blocks"][0]["bytes"], b"owned123".hex().upper())
        self.assertEqual(restored["deallocations"], ["saved"])

    def test_external_symbols_and_module_memory_are_rip_relative(self):
        from iced_x86 import Decoder
        source = '[ENABLE]\nalloc(cave,100)\ncave:\nmov eax,[external]\nmov ecx,["owned.exe"+30]\n[DISABLE]\ndealloc(*)'
        result = link_program(prepare_program(source), Memory(), {"external": 0x140001000}, {"cave": {"address": 0x140002000, "size": 256}}, assembler=self.assembler)
        instructions = list(Decoder(64, bytes.fromhex(result["blocks"][0]["bytes"]), ip=0x140002000))
        self.assertEqual([instruction.ip_rel_memory_address for instruction in instructions], [0x140001000, 0x140000030])

    def test_typed_float_bit_pattern_can_be_zero_extended(self):
        source = '[ENABLE]\nalloc(cave,100)\ncave:\ndq (float)1.0\n[DISABLE]\ndealloc(*)'
        result = link_program(prepare_program(source), Memory(), allocations={"cave": {"address": 0x1000, "size": 256}}, assembler=self.assembler)
        self.assertEqual(result["blocks"][0]["bytes"], "0000803F00000000")
        with self.assertRaisesRegex(ProgramError, "does not fit"):
            prepare_program(source.replace("dq (float)", "dd (double)"))

    def test_mixed_case_local_label_does_not_replace_register(self):
        source = '[ENABLE]\nalloc(cave,100)\nlabel(aL)\ncave:\nmov al,1\njmp aL\naL:\nret\n[DISABLE]\ndealloc(*)'
        result = link_program(prepare_program(source), Memory(), allocations={"cave": {"address": 0x140002000, "size": 256}}, assembler=self.assembler)
        self.assertTrue(result["blocks"][0]["bytes"].startswith("B001EB00C3"))

    def test_implicit_named_labels_and_unsized_dword_operands(self):
        source = '[ENABLE]\nalloc(cave,100)\nlabel(flag)\ncave:\nflag:\ndd 0\ncmp [rcx+67C-2C],1\nje @Player\ninc [rax]\n@Player:\nmov [rcx+67C],(float)100\n[DISABLE]\ndealloc(*)'
        result = link_program(prepare_program(source), Memory(), allocations={"cave": {"address": 0x140002000, "size": 256}}, assembler=self.assembler)
        self.assertIn("83B95006000001", result["blocks"][0]["bytes"])

    def test_assert_snapshot_race_rejected(self):
        class RacingMemory(Memory):
            def read(self, address, size):
                data = super().read(address, size)
                if address == 0x140001000 and size == 2:
                    self.seed(address, b"\x90")
                return data

        memory = RacingMemory()
        memory.seed(0x140001000, bytes.fromhex("89 5F 44 48 8B 5C 24 30"))
        source = OWNED_HOOK.replace("alloc(cave", "assert(anchor,89 5F)\nalloc(cave")
        with self.assertRaisesRegex(ProgramError, "changed while linking"):
            link_program(prepare_program(source), memory, allocations={"cave": {"address": 0x140002000, "size": 4096}}, assembler=self.assembler)

    def test_allocation_only_disable_has_empty_patch_plan(self):
        source = '[ENABLE]\nalloc(cave,100)\ncave:\nret\n[DISABLE]\ndealloc(*)'
        result = link_program(prepare_program(source), Memory(), allocations={"cave": {"address": 0x1000, "size": 256}}, phase="disable", assembler=self.assembler)
        self.assertEqual(result["blocks"], [])
        self.assertEqual(result["deallocations"], ["cave"])

    def test_pure_literal_allocation_is_data_and_mixed_is_code(self):
        source = '[ENABLE]\nalloc(data,100)\nalloc(code,100)\nlabel(flag)\ndata:\nflag:\ndb 0\ndq (float)1.0\ncode:\nmov al,[flag]\nret\n[DISABLE]\ndealloc(*)'
        program = prepare_program(source)
        preflight = preflight_program(program, Memory())
        self.assertEqual([request['executable'] for request in preflight['allocation_requests']], [False, True])
        result = link_program(program, Memory(), allocations={"data": {"address": 0x1000, "size": 256, "executable": False}, "code": {"address": 0x2000, "size": 256, "executable": True}}, assembler=self.assembler)
        self.assertFalse(result['blocks'][0]['executable'])
        self.assertTrue(result['blocks'][1]['executable'])
        with self.assertRaisesRegex(ProgramError, 'Code/unknown'):
            link_program(program, Memory(), allocations={"data": {"address": 0x1000, "size": 256}, "code": {"address": 0x2000, "size": 256, "executable": False}}, assembler=self.assembler)
        code_bytes = prepare_program(source.replace('mov al,[flag]', 'jmp flag'))
        self.assertTrue(code_bytes['allocation_executable']['data'])

    def test_mixed_allocations_and_self_stores_require_writable_code(self):
        source = '[ENABLE]\nalloc(cave,100)\nlabel(flag)\ncave:\nflag:\ndb 0\nmov [flag],al\nret\n[DISABLE]\ndealloc(*)'
        program = prepare_program(source)
        self.assertEqual(program['allocation_executable'], {'cave': True})
        self.assertEqual(program['allocation_writable'], {'cave': True})
        result = preflight_program(program, Memory())
        self.assertTrue(result['allocation_requests'][0]['writable'])
        with self.assertRaisesRegex(ProgramError, 'read-only code'):
            link_program(program, Memory(), allocations={'cave': {'address': 0x1000, 'size': 256, 'executable': True, 'writable': False}}, assembler=self.assembler)
        pure = prepare_program(source.replace('flag:\ndb 0\nmov [flag],al', 'flag:\nxor eax,eax'))
        self.assertFalse(pure['allocation_writable']['cave'])
        self_store = prepare_program(source.replace('flag:\ndb 0\nmov [flag],al', 'flag:\nmov [flag],al'))
        self.assertTrue(self_store['allocation_writable']['cave'])
        alias_store = prepare_program(source.replace('flag:\ndb 0\nmov [flag],al', 'flag:\nmov rax,flag\nmov [rax],cl'))
        self.assertTrue(alias_store['allocation_writable']['cave'])
        aligned = prepare_program(source.replace('flag:\ndb 0\nmov [flag],al', 'flag:\nalign 10 CC\nret'))
        self.assertTrue(aligned['allocation_writable']['cave'])

    def test_implicit_masked_writers_require_writable_executable_allocation(self):
        from iced_x86 import Decoder, InstructionInfoFactory, OpAccess
        for instruction in ('maskmovdqu xmm0,xmm1', 'vmaskmovdqu xmm0,xmm1'):
            with self.subTest(instruction=instruction):
                source = '[ENABLE]\nalloc(cave,100)\ncave:\nmov rdi,cave\n' + instruction + '\nret\n[DISABLE]\ndealloc(*)'
                program = prepare_program(source)
                self.assertTrue(program['allocation_executable']['cave'])
                self.assertTrue(program['allocation_writable']['cave'])
                with self.assertRaisesRegex(ProgramError, 'read-only code'):
                    link_program(program, Memory(), allocations={'cave': {'address': 0x1000, 'size': 256, 'executable': True, 'writable': False}}, assembler=self.assembler)
                linked = link_program(program, Memory(), allocations={'cave': {'address': 0x1000, 'size': 256, 'executable': True, 'writable': True}}, assembler=self.assembler)
                decoded = list(Decoder(64, bytes.fromhex(linked['blocks'][0]['bytes'])))
                masked_write = InstructionInfoFactory().info(decoded[1]).used_memory()
                self.assertTrue(any(access.access in {OpAccess.WRITE, OpAccess.COND_WRITE, OpAccess.READ_WRITE, OpAccess.READ_COND_WRITE} for access in masked_write))

    def test_unproven_mnemonics_default_to_writable_code(self):
        for instruction in ('enter 0,0', 'future_writer rax'):
            with self.subTest(instruction=instruction):
                source = '[ENABLE]\nalloc(cave,100)\ncave:\n' + instruction + '\nret\n[DISABLE]\ndealloc(*)'
                program = prepare_program(source)
                self.assertTrue(program['allocation_writable']['cave'])
                self.assertTrue(preflight_program(program, Memory())['allocation_requests'][0]['writable'])
        # ENTER is an actual NASM instruction with an implicit stack store; the
        # unknown token exercises the conservative future-instruction default.
        self.assertEqual(self.assembler.assemble('BITS 64\nenter 0,0\n').hex(), 'c8000000')

    def test_proven_mov_add_jump_code_stays_rx(self):
        source = '[ENABLE]\nalloc(cave,100)\ncave:\nmov eax,ecx\nadd eax,64\njmp 2000\n[DISABLE]\ndealloc(*)'
        program = prepare_program(source)
        self.assertEqual(program['allocation_executable'], {'cave': True})
        self.assertEqual(program['allocation_writable'], {'cave': False})
        linked = link_program(program, Memory(), allocations={'cave': {'address': 0x1000, 'size': 256, 'executable': True, 'writable': False}}, assembler=self.assembler)
        self.assertTrue(linked['blocks'][0]['executable'])
        self.assertTrue(linked['blocks'][0]['bytes'].startswith('89C883C064E9'))

    def test_parent_owned_literal_data_requires_complete_trusted_provenance(self):
        source = '[ENABLE]\nflag:\ndb 1 2\n[DISABLE]\nflag:\ndb 0 0'
        program = prepare_program(source)
        kwargs = dict(symbols={'flag': 0x1000}, assembler=self.assembler)
        for ranges in (None, [(0x1000, 1)], [(0x1001, 1)]):
            result = link_program(program, Memory(), owned_data_ranges=ranges, **kwargs)
            self.assertTrue(result['blocks'][0]['executable'])
            self.assertTrue(result['blocks'][0]['requires_coordinator'])
        result = link_program(program, Memory(), owned_data_ranges=[(0x1000, 256)], **kwargs)
        self.assertFalse(result['blocks'][0]['executable'])
        self.assertFalse(result['requires_coordinator'])
        patched = prepare_program(source.replace('db 1 2', 'mov al,1'))
        result = link_program(patched, Memory(), owned_data_ranges=[(0x1000, 256)], **kwargs)
        self.assertTrue(result['blocks'][0]['executable'])
        self.assertTrue(result['requires_coordinator'])

    def test_data_provenance_cannot_be_serialized_or_forged_with_bad_ranges(self):
        program = prepare_program('[ENABLE]\n1000:\ndb 1\n[DISABLE]\n1000:\ndb 0')
        forged = dict(program, owned_data_ranges=[(0x1000, 256)])
        with self.assertRaises(ProgramError):
            validate_program(forged)
        for ranges in ([(0x1000, True)], [(0, 10)], [(0x1000, -1)], '1000,100'):
            with self.subTest(ranges=ranges), self.assertRaises(ProgramError):
                link_program(program, Memory(), assembler=self.assembler, owned_data_ranges=ranges)

    def test_interleaved_literal_nodes_have_exact_remote_spans(self):
        source = '''[ENABLE]
alloc(cave,100)
label(byteflag,wordflag,floatflag,qwordflag,sparse)
cave:
nop
byteflag:
db 0 1
align 10 CC
wordflag:
dw 1122
mov eax,#2
floatflag:
dd (float)1.5 #7
qwordflag:
dq 0 1
readmem(anchor,3)
reassemble(anchor)
jmp far sparse
cave+80:
sparse:
db "AB"
registersymbol(byteflag,wordflag,floatflag,qwordflag,sparse)
[DISABLE]
unregistersymbol(*)
dealloc(*)
'''
        memory = Memory()
        memory.seed(0x140001000, bytes.fromhex('90 90 90'))
        linked = link_program(prepare_program(source), memory, symbols={'anchor': 0x140001000},
                              allocations={'cave': {'address': 0x1003, 'size': 256, 'executable': True, 'writable': True}}, assembler=self.assembler)
        expected = [{'address': linked['exports'][name], 'size': size, 'allocation': 'cave'}
                    for name, size in (('byteflag', 2), ('wordflag', 2), ('floatflag', 8), ('qwordflag', 16), ('sparse', 2))]
        self.assertEqual(linked['literal_data_ranges'], expected)
        self.assertEqual([item for block in linked['blocks'] for item in block['literal_data_ranges']], expected)
        self.assertEqual(linked['exports']['byteflag'], 0x1004)
        self.assertEqual(linked['exports']['wordflag'], 0x1010)
        self.assertEqual(linked['exports']['floatflag'], 0x1017)  # Packed, naturally unaligned dd is legitimate data.
        self.assertEqual(linked['exports']['sparse'], 0x1083)
        spans = {(item['address'], item['address'] + item['size']) for item in expected}
        self.assertFalse(any(start <= 0x1006 < end for start, end in spans))  # Alignment padding.
        self.assertFalse(any(start <= 0x1012 < end for start, end in spans))  # MOV instruction.
        self.assertFalse(any(start <= 0x102F < end for start, end in spans))  # readmem/reassemble and far-pointer bytes.

    def test_symbolic_data_and_external_literals_do_not_mint_owned_spans(self):
        source = '[ENABLE]\nalloc(cave,100)\ncave:\ndq anchor\nreadmem(anchor,1)\nreassemble(anchor)\nalign 10 00\nret\n2000:\ndd 0\n[DISABLE]\n2000:\ndd 0\ndealloc(*)'
        memory = Memory()
        memory.seed(0x140001000, b'\x90')
        linked = link_program(prepare_program(source), memory, symbols={'anchor': 0x140001000},
                              allocations={'cave': {'address': 0x1000, 'size': 256}}, assembler=self.assembler)
        self.assertEqual(linked['literal_data_ranges'], [])
        self.assertTrue(all(block['literal_data_ranges'] == [] for block in linked['blocks']))
        self.assertFalse(linked['blocks'][1]['data_semantics'])

    def test_executable_literal_children_keep_coordination_and_span_bounds(self):
        provider = prepare_program('[ENABLE]\nalloc(cave,100)\nlabel(flag)\ncave:\nnop\nflag:\ndd 0\nret\nregistersymbol(flag)\n[DISABLE]\nunregistersymbol(*)\ndealloc(*)')
        memory = Memory()
        allocation = {'cave': {'address': 0x1000, 'size': 256, 'executable': True, 'writable': True}}
        parent = link_program(provider, memory, allocations=allocation, assembler=self.assembler)
        for block in parent['blocks']:
            memory.seed(block['address'], bytes.fromhex(block['bytes']))
        span = parent['literal_data_ranges'][0]
        trusted = [(span['address'], span['size'], 0x1000, 256)]
        child_source = '[ENABLE]\nflag:\ndd 1\n[DISABLE]\nflag:\ndd 0'
        child = prepare_program(child_source)
        untrusted = link_program(child, memory, parent['exports'], assembler=self.assembler)
        self.assertFalse(untrusted['blocks'][0]['data_semantics'])
        linked = link_program(child, memory, parent['exports'], assembler=self.assembler, owned_executable_data_ranges=trusted)
        self.assertTrue(linked['blocks'][0]['data_semantics'])
        self.assertTrue(linked['blocks'][0]['literal_data'])
        self.assertTrue(linked['blocks'][0]['executable'])
        self.assertTrue(linked['blocks'][0]['requires_coordinator'])
        self.assertEqual(linked['literal_data_ranges'], [])
        for shift in ('+1', '+4', '-1'):
            with self.subTest(shift=shift):
                shifted = prepare_program(child_source.replace('flag:', 'flag' + shift + ':'))
                result = link_program(shifted, memory, parent['exports'], assembler=self.assembler, owned_executable_data_ranges=trusted)
                self.assertFalse(result['blocks'][0]['data_semantics'])
                self.assertTrue(result['blocks'][0]['requires_coordinator'])
        for body in ('mov eax,1', 'align 2 00\ndd 1', 'readmem(flag,4)', 'reassemble(flag)'):
            with self.subTest(body=body):
                mixed = prepare_program(child_source.replace('dd 1', body))
                result = link_program(mixed, memory, parent['exports'], assembler=self.assembler, owned_executable_data_ranges=trusted)
                self.assertFalse(result['blocks'][0]['data_semantics'])

    def test_executable_literal_provenance_is_not_serializable(self):
        program = prepare_program('[ENABLE]\nalloc(cave,100)\ncave:\ndd 0\n[DISABLE]\ndealloc(*)')
        for key, value in (('literal_data_ranges', [{'address': 0x1000, 'size': 4, 'allocation': 'cave'}]),
                           ('owned_executable_data_ranges', [[0x1000, 4, 0x1000, 256]])):
            forged = dict(program, **{key: value})
            with self.subTest(key=key), self.assertRaises(ProgramError):
                link_program(forged, Memory(), allocations={'cave': {'address': 0x1000, 'size': 256}}, assembler=self.assembler)
        invalid_ranges = ([(0x1000, True, 0x1000, 256)], [(0x1000, 4)],
                          [(0xFFF, 4, 0x1000, 256)], [(0x10FE, 4, 0x1000, 256)],
                          [(0x1000, 4, 0x1000, -1)], [(0xFFFFFFFFFFFFFFFF, 4, 0xFFFFFFFFFFFFFFFF, 4)])
        for ranges in invalid_ranges:
            with self.subTest(ranges=ranges), self.assertRaises(ProgramError):
                link_program(program, Memory(), allocations={'cave': {'address': 0x1000, 'size': 256}}, assembler=self.assembler,
                             owned_executable_data_ranges=ranges)

    def test_forged_assembler_literal_footer_cannot_expand_provenance(self):
        real = self.assembler

        class ForgedFooter:
            def assemble(self, source):
                binary = bytearray(real.assemble(source))
                # Last two footer addresses delimit the sole db node. Expanding
                # it to include the following NOP must fail source-length proof.
                start = int.from_bytes(binary[-16:-8], 'little')
                binary[-8:] = (start + 2).to_bytes(8, 'little')
                return bytes(binary)

        source = '[ENABLE]\nalloc(cave,100)\ncave:\ndb 0\nnop\n[DISABLE]\ndealloc(*)'
        with self.assertRaisesRegex(ProgramError, 'literal data provenance'):
            link_program(prepare_program(source), Memory(), allocations={'cave': {'address': 0x1000, 'size': 256}}, assembler=ForgedFooter())

    def test_reassemble_preserves_rip_relative_target(self):
        from iced_x86 import Decoder
        source = "[ENABLE]\nalloc(cave,100,anchor)\ncave:\nreassemble(anchor)\n[DISABLE]\ndealloc(*)"
        memory = Memory()
        memory.seed(0x140001000, bytes.fromhex("48 8B 05 20 00 00 00"))
        result = link_program(prepare_program(source), memory, {"anchor": 0x140001000}, {"cave": {"address": 0x140003000, "size": 256}}, assembler=self.assembler)
        instruction = Decoder(64, bytes.fromhex(result["blocks"][0]["bytes"]), ip=0x140003000).decode()
        self.assertEqual(instruction.ip_rel_memory_address, 0x140001027)

    def test_far_jump_and_call_use_absolute_indirect_targets(self):
        from iced_x86 import Decoder
        source = '[ENABLE]\nalloc(cave,100)\ncave:\nret\n1000:\njmp far cave\nnop\n2000:\ncall far cave\n[DISABLE]\n1000:\ndb 90\ndealloc(*)'
        target = 0x7FF800004000
        result = link_program(prepare_program(source), Memory(), allocations={"cave": {"address": target, "size": 256}}, assembler=self.assembler)
        jump = bytes.fromhex(result["blocks"][1]["bytes"])
        self.assertEqual(jump, bytes.fromhex('FF 25 00 00 00 00') + target.to_bytes(8, 'little') + b'\x90')
        call = bytes.fromhex(result["blocks"][2]["bytes"])
        instructions = list(Decoder(64, call[:8], ip=0x2000))
        self.assertEqual(instructions[0].ip_rel_memory_address, 0x2008)
        self.assertEqual(instructions[1].near_branch_target, 0x2010)
        self.assertEqual(call[8:], target.to_bytes(8, 'little'))

    def test_missing_allocation_and_overflow_fail_before_publication(self):
        memory = Memory()
        with self.assertRaisesRegex(ProgramError, "allocation"):
            link_program(prepare_program(OWNED_HOOK), memory, assembler=self.assembler)
        source = "[ENABLE]\nalloc(cave,1)\ncave:\n dq 0\n[DISABLE]\ndealloc(*)"
        with self.assertRaisesRegex(ProgramError, "boundary"):
            link_program(prepare_program(source), memory, allocations={"cave": {"address": 0x1000, "size": 1}}, assembler=self.assembler)

    def test_pinned_assembler_hash(self):
        with self.assertRaisesRegex(AssemblyError, "SHA-256"):
            NasmAssembler(find_nasm(), expected_sha256="0" * 64)

    def test_cross_section_branch_displacements_are_proved_independently(self):
        for instruction, target in (('jmp short cave', 0x2000), ('je short cave', 0x2000),
                                    ('loop cave', 0x2000), ('jmp cave', 0x7FF800004000),
                                    ('call cave', 0x7FF800004000)):
            with self.subTest(instruction=instruction):
                source = '[ENABLE]\nalloc(cave,100)\ncave:\nret\n1000:\n' + instruction + '\n[DISABLE]\n1000:\ndb 0\ndealloc(*)'
                with self.assertRaisesRegex(ProgramError, 'displacement is out of range'):
                    link_program(prepare_program(source), Memory(), allocations={'cave': {'address': target, 'size': 256}}, assembler=self.assembler)

    def test_local_anonymous_and_indirect_branch_forms_preserve_their_targets(self):
        source = '[ENABLE]\nalloc(cave,100)\nlabel(aL,ending)\ncave:\njmp short aL\naL:\ncall ending\n@@:\nloop @b\nending:\njmp qword rax\nregistersymbol(aL,ending)\n[DISABLE]\nunregistersymbol(*)\ndealloc(*)'
        linked = link_program(prepare_program(source), Memory(), allocations={'cave': {'address': 0x1000, 'size': 256}}, assembler=self.assembler)
        from iced_x86 import Decoder
        decoded = list(Decoder(64, bytes.fromhex(linked['blocks'][0]['bytes']), ip=0x1000))
        self.assertEqual(decoded[0].near_branch_target, linked['exports']['aL'])
        self.assertEqual(decoded[1].near_branch_target, linked['exports']['ending'])
        self.assertEqual(decoded[2].near_branch_target, decoded[2].ip)
        self.assertEqual(decoded[-1].len, 2)

    def test_static_memory_displacements_are_proved_against_source_addresses(self):
        source = '[ENABLE]\nalloc(cave,100,anchor)\ncave:\nmov rax,[external]\nret\n[DISABLE]\ndealloc(*)'
        with self.assertRaisesRegex(ProgramError, 'static memory operand.*out of range'):
            link_program(prepare_program(source), Memory(), {'anchor': 0x1000, 'external': 0x7FF800004000},
                         {'cave': {'address': 0x110000, 'size': 256}}, assembler=self.assembler)
        # A true absolute form that fits, and register-dependent addressing,
        # remain admitted rather than being mistaken for RIP-relative fields.
        source = '[ENABLE]\n1000:\nmov eax,[abs 2000]\nmov eax,[rax+20]\n[DISABLE]\n1000:\ndb 0'
        linked = link_program(prepare_program(source), Memory(), assembler=self.assembler)
        from iced_x86 import Decoder
        instructions = list(Decoder(64, bytes.fromhex(linked['blocks'][0]['bytes']), ip=0x1000))
        self.assertFalse(instructions[0].is_ip_rel_memory_operand)
        self.assertEqual(instructions[0].memory_displacement, 0x2000)
        self.assertEqual(instructions[1].memory_displacement, 0x20)

    def test_symbol_math_keeps_its_binding_during_displacement_proof(self):
        source = '[ENABLE]\nalloc(cave,100)\nlabel(flag)\ncave:\nmov eax,[flag+4]\njmp short flag+4\nflag:\ndd 0 0\nregistersymbol(flag)\n[DISABLE]\nunregistersymbol(*)\ndealloc(*)'
        linked = link_program(prepare_program(source), Memory(), allocations={'cave': {'address': 0x1000, 'size': 256}}, assembler=self.assembler)
        from iced_x86 import Decoder
        instructions = list(Decoder(64, bytes.fromhex(linked['blocks'][0]['bytes'])[:8], ip=0x1000))
        self.assertEqual(instructions[0].ip_rel_memory_address, linked['exports']['flag'] + 4)
        self.assertEqual(instructions[1].near_branch_target, linked['exports']['flag'] + 4)

    def test_register_displacement_symbols_cannot_be_silently_truncated(self):
        source = '[ENABLE]\nalloc(cave,100,anchor)\ncave:\nmov rax,[rax+external]\nret\n[DISABLE]\ndealloc(*)'
        for bitness, target in ((64, 0x7FF800004000), (32, 0x140000000)):
            with self.subTest(bitness=bitness):
                code = source if bitness == 64 else source.replace('rax', 'eax')
                with self.assertRaisesRegex(ProgramError, 'memory displacement.*(out of range|address width)'):
                    link_program(prepare_program(code, bitness=bitness), Memory(), {'anchor': 0x1000, 'external': target},
                                 {'cave': {'address': 0x110000, 'size': 256}}, assembler=self.assembler)

    def test_signed_scaled_and_deferred_displacements_keep_their_values(self):
        source = '[ENABLE]\ndefine(offset,flag-cave)\nalloc(cave,100)\nlabel(flag)\ncave:\nmov eax,[rax-38]\nmov eax,[rax+rcx*4+offset]\nflag:\ndd 0\nregistersymbol(offset)\n[DISABLE]\nunregistersymbol(*)\ndealloc(*)'
        linked = link_program(prepare_program(source), Memory(), allocations={'cave': {'address': 0x1000, 'size': 256}}, assembler=self.assembler)
        from iced_x86 import Decoder
        instructions = list(Decoder(64, bytes.fromhex(linked['blocks'][0]['bytes'])[:-4], ip=0x1000))
        self.assertEqual(instructions[0].memory_displacement, (1 << 64) - 0x38)
        self.assertEqual(instructions[1].memory_displacement, linked['exports']['offset'])
        self.assertEqual(instructions[1].memory_index_scale, 4)
        self.assertEqual(linked['exports']['offset'], sum(instruction.len for instruction in instructions))


class DryLinkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.assembler = NasmAssembler()
        except AssemblyError as exc:
            raise unittest.SkipTest(str(exc))

    class ReadOnlyMemory(Memory):
        def __init__(self):
            super().__init__()
            self.mutations = []
            self.allowed = [(0x1000, 0x3000), (0x140000000, 0x140100000)]

        def read(self, address, size):
            if not any(start <= address < address + size <= end for start, end in self.allowed):
                raise AssertionError("Dry linker read an unallocated placeholder from the target")
            return super().read(address, size)

        def _mutation(self, *args, **kwargs):
            self.mutations.append((args, kwargs))
            raise AssertionError("Dry linker called a target mutation API")

        allocate = write = protect = flush_instruction_cache = release = close = _mutation

    def test_complete_hook_checks_real_nasm_and_private_disable_overlay(self):
        source = OWNED_HOOK.replace('[DISABLE]\nanchor:', '[DISABLE]\nassert(anchor,E9 ?? ?? ?? ?? 90 90 90)\nanchor:')
        memory = self.ReadOnlyMemory()
        original = bytes.fromhex('89 5F 44 48 8B 5C 24 30')
        memory.seed(0x140001000, original)
        snapshot = dict(memory.data)
        result = dry_link_program(prepare_program(source), memory, assembler=self.assembler)
        self.assertEqual(result['schema'], 'ct2trainer-aa-dry-link/v1')
        self.assertTrue(result['dry_run'])
        self.assertFalse(result['publishable'])
        self.assertIn('synthetic', result['diagnostics'][0])
        allocation = result['synthetic_allocations']['cave']
        self.assertLessEqual(abs(allocation['address'] - 0x140001000), 0x7FFF0000)
        self.assertFalse(0x140000000 <= allocation['address'] < 0x140100000)
        self.assertEqual(result['enable']['blocks'][0]['original'], '00' * len(bytes.fromhex(result['enable']['blocks'][0]['bytes'])))
        self.assertEqual(result['disable']['blocks'][0]['bytes'], original.hex().upper())
        self.assertEqual(result['disable']['guards'][0]['bytes'], result['enable']['blocks'][1]['bytes'])
        self.assertEqual(memory.data, snapshot)
        self.assertFalse(memory.mutations)

    def test_bad_instruction_in_either_phase_is_rejected_without_mutation(self):
        source = '[ENABLE]\n1000:\nnop\n[DISABLE]\n1000:\nnop'
        for phase in ('[ENABLE]', '[DISABLE]'):
            with self.subTest(phase=phase):
                memory = self.ReadOnlyMemory()
                memory.seed(0x1000, b'\x90')
                bad = source.replace(phase + '\n1000:\nnop', phase + '\n1000:\nnot_a_real_instruction rax')
                with self.assertRaisesRegex(ProgramError, 'NASM rejected'):
                    dry_link_program(prepare_program(bad), memory, assembler=self.assembler)
                self.assertEqual(memory.read(0x1000, 1), b'\x90')
                self.assertFalse(memory.mutations)

    def test_private_allocation_bounds_and_short_branch_are_checked(self):
        cases = (('[ENABLE]\nalloc(cave,1)\ncave:\ndq 0\n[DISABLE]\ndealloc(*)', 'boundary'),
                 ('[ENABLE]\nalloc(cave,100,anchor)\ncave:\nret\nanchor:\njmp short cave\n[DISABLE]\nanchor:\ndb 90 90\ndealloc(*)', 'displacement is out of range'))
        for source, reason in cases:
            with self.subTest(reason=reason):
                memory = self.ReadOnlyMemory()
                with self.assertRaisesRegex(ProgramError, reason):
                    dry_link_program(prepare_program(source), memory, {'anchor': 0x140001000}, assembler=self.assembler)
                self.assertFalse(memory.mutations)

    def test_multiple_placeholders_fit_32_bit_near_bounds(self):
        source = '[ENABLE]\nalloc(first,100,anchor)\nalloc(second,100,anchor)\nfirst:\nret\nsecond:\nret\nanchor:\njmp first\n[DISABLE]\nanchor:\ndb 90 90 90 90 90\ndealloc(*)'
        memory = self.ReadOnlyMemory()
        memory.allowed = [(0xFFFF0000, 0x100000000)]
        memory.seed(0xFFFF0000, b'\x90' * 5)
        result = dry_link_program(prepare_program(source, bitness=32), memory, {'anchor': 0xFFFF0000}, assembler=self.assembler)
        first, second = result['synthetic_allocations'].values()
        self.assertNotEqual(first['address'], second['address'])
        for allocation in (first, second):
            self.assertLessEqual(allocation['address'] + allocation['size'], 0x100000000)
            self.assertLessEqual(abs(allocation['address'] - 0xFFFF0000), 0x7FFF0000)
        self.assertFalse(memory.mutations)

    def test_provenance_remains_controller_input_and_target_bytes_unchanged(self):
        memory = self.ReadOnlyMemory()
        source = '[ENABLE]\nflag:\ndd 1\n[DISABLE]\nflag:\ndd 0'
        result = dry_link_program(prepare_program(source), memory, {'flag': 0x1000},
                                  owned_executable_data_ranges=[(0x1000, 4, 0x1000, 256)], assembler=self.assembler)
        self.assertTrue(result['enable']['blocks'][0]['data_semantics'])
        self.assertTrue(result['enable']['blocks'][0]['requires_coordinator'])
        self.assertEqual(memory.read(0x1000, 4), bytes(4))
        self.assertFalse(memory.mutations)
        forged = dict(prepare_program(source), synthetic_allocations=result['synthetic_allocations'])
        memory.reads.clear()
        with self.assertRaisesRegex(ProgramError, 'metadata/operations'):
            dry_link_program(forged, memory, {'flag': 0x1000}, assembler=self.assembler)
        self.assertFalse(memory.reads)

    def test_forged_assembler_bounds_fail_without_target_mutation(self):
        real = self.assembler

        class ForgedFooter:
            def assemble(self, source):
                binary = bytearray(real.assemble(source))
                # One section plus one literal node: first footer value is the
                # payload offset. It may never select bytes beyond the payload.
                binary[-32:-24] = len(binary).to_bytes(8, 'little')
                return bytes(binary)

        memory = self.ReadOnlyMemory()
        source = '[ENABLE]\n1000:\ndb 1\n[DISABLE]\n1000:\ndb 0'
        with self.assertRaisesRegex(ProgramError, 'out of bounds'):
            dry_link_program(prepare_program(source), memory, assembler=ForgedFooter())
        self.assertEqual(memory.read(0x1000, 1), b'\0')
        self.assertFalse(memory.mutations)

    def test_altered_branch_bytes_cannot_borrow_valid_source_metadata(self):
        real = self.assembler

        class AlteredDisplacement:
            def assemble(self, source):
                binary = bytearray(real.assemble(source))
                self.assert_jump(binary)
                binary[1:5] = bytes(4)  # Jump to the next instruction instead of 2000.
                return bytes(binary)

            @staticmethod
            def assert_jump(binary):
                if binary[0] != 0xE9:
                    raise AssertionError('Expected an owned direct JMP fixture')

        memory = self.ReadOnlyMemory()
        source = '[ENABLE]\n1000:\njmp 2000\n[DISABLE]\n1000:\ndb 0 0 0 0 0'
        with self.assertRaisesRegex(ProgramError, 'does not reach its source target'):
            dry_link_program(prepare_program(source), memory, assembler=AlteredDisplacement())
        self.assertFalse(memory.mutations)

    def test_readmem_and_reassemble_use_actual_reads_and_private_addresses(self):
        source = '[ENABLE]\nalloc(cave,100,anchor)\ncave:\nreadmem(anchor,3)\nreassemble(anchor+3)\nret\n[DISABLE]\ndealloc(*)'
        memory = self.ReadOnlyMemory()
        memory.seed(0x140001000, bytes.fromhex('90 90 90 48 8B 05 20 00 00 00'))
        snapshot = dict(memory.data)
        result = dry_link_program(prepare_program(source), memory, {'anchor': 0x140001000}, assembler=self.assembler)
        from iced_x86 import Decoder
        block = result['enable']['blocks'][0]
        self.assertTrue(block['bytes'].startswith('909090'))
        relocated = Decoder(64, bytes.fromhex(block['bytes'])[3:], ip=block['address'] + 3).decode()
        self.assertEqual(relocated.ip_rel_memory_address, 0x14000102A)
        self.assertEqual(memory.data, snapshot)
        self.assertFalse(memory.mutations)

    def test_dry_rip_relative_overflow_is_rejected_without_target_mutation(self):
        memory = self.ReadOnlyMemory()
        source = '[ENABLE]\nalloc(cave,100,anchor)\ncave:\nmov rax,[external]\nret\n[DISABLE]\ndealloc(*)'
        with self.assertRaisesRegex(ProgramError, 'static memory operand.*out of range'):
            dry_link_program(prepare_program(source), memory, {'anchor': 0x1000, 'external': 0x7FF800004000}, assembler=self.assembler)
        self.assertFalse(memory.mutations)

    def test_dry_symbolic_register_overflow_is_rejected_without_target_mutation(self):
        memory = self.ReadOnlyMemory()
        source = '[ENABLE]\nalloc(cave,100,anchor)\ncave:\nmov rax,[rax+external]\nret\n[DISABLE]\ndealloc(*)'
        with self.assertRaisesRegex(ProgramError, 'memory displacement.*out of range'):
            dry_link_program(prepare_program(source), memory, {'anchor': 0x1000, 'external': 0x7FF800004000}, assembler=self.assembler)
        self.assertFalse(memory.mutations)


class _FlakyRoot:
    """Stub of a temp dir whose rmdir fails N times with a sharing violation."""

    def __init__(self, failures):
        self.failures = failures
        self.attempts = 0

    def iterdir(self):
        return []

    def rmdir(self):
        self.attempts += 1
        if self.attempts <= self.failures:
            raise PermissionError(32, "Sharing violation", None, None)


class TempCleanupTests(unittest.TestCase):
    def test_removes_a_nested_tree(self):
        root = Path(tempfile.mkdtemp(prefix="ct2trainer-nasm-cleanup-"))
        try:
            (root / "program.asm").write_text("bits 64\n")
            nested = root / "sub"
            nested.mkdir()
            (nested / "program.bin").write_bytes(b"\x90")
            self.assertTrue(assembler._remove_temp_dir_quietly(root, attempts=2, delay=0.01))
            self.assertFalse(root.exists())
        finally:
            if root.exists():
                shutil.rmtree(root, ignore_errors=True)

    def test_sharing_violation_is_retried_until_released(self):
        sleeps = []
        with mock.patch.object(assembler.time, "sleep", side_effect=lambda s: sleeps.append(s)):
            root = _FlakyRoot(failures=2)
            self.assertTrue(assembler._remove_temp_dir_quietly(root, attempts=4, delay=0.1))
        self.assertEqual(root.attempts, 3)
        self.assertEqual(sleeps, [0.1, 0.1])

    def test_persistent_sharing_violation_returns_false_without_raising(self):
        with mock.patch.object(assembler.time, "sleep"):
            root = _FlakyRoot(failures=99)
            self.assertFalse(assembler._remove_temp_dir_quietly(root, attempts=3, delay=0.1))
        self.assertEqual(root.attempts, 3)


ALLOCATION_ONLY = "[ENABLE]\nalloc(memory,0x100)\nregistersymbol(memory)\n[DISABLE]\nunregistersymbol(memory)\ndealloc(memory)"


class AllocationOnlyProgramTests(unittest.TestCase):
    """WP-29: a named allocation-only init profile (alloc + register, no
    code/data) is a supported re-enabled program, never a one-shot."""

    def test_prepare_marks_allocation_only_and_provides(self):
        program = prepare_program(ALLOCATION_ONLY, "Target.exe")
        self.assertTrue(program["allocation_only"])
        self.assertFalse(program["one_shot"])
        self.assertEqual(program["provides"], ["memory"])
        self.assertEqual(program["allocations"], ["memory"])
        # No cursor ever enters the allocation, so the capability heuristic
        # stays conservative (RWX) rather than proving a data-only profile.
        self.assertTrue(program["allocation_executable"]["memory"])
        self.assertTrue(program["allocation_writable"]["memory"])
        validate_program(program)

    def test_one_shot_allocation_only_still_refused(self):
        # An empty DISABLE section makes the program a one-shot, which may
        # never be allocation-only.
        with self.assertRaisesRegex(ProgramError, "Enable section has no executable patch or data."):
            prepare_program("[ENABLE]\nalloc(memory,0x100)\n[DISABLE]\n", "Target.exe")

    def test_preflight_requests_the_owned_allocation(self):
        program = prepare_program(ALLOCATION_ONLY, "Target.exe")
        result = preflight_program(program, Memory())
        # No cursor ever enters the allocation, so the capability heuristic
        # stays conservative (RWX), mirroring prepare_program's flags.
        self.assertEqual(result["allocation_requests"],
                         [{"name": "memory", "size": 256, "near": None, "executable": True, "writable": True}])
        self.assertEqual(result["guards"], [])


class AllocationOnlyLinkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.assembler = NasmAssembler()
        except AssemblyError as exc:
            raise unittest.SkipTest(str(exc))

    def test_dry_link_yields_empty_blocks_and_cleanup_lists(self):
        memory = Memory()
        result = dry_link_program(prepare_program(ALLOCATION_ONLY, "Target.exe"), memory, assembler=self.assembler)
        self.assertEqual(result["enable"]["blocks"], [])
        self.assertIn("memory", result["synthetic_allocations"])
        self.assertEqual(result["disable"]["blocks"], [])
        self.assertEqual(result["disable"]["deallocations"], ["memory"])
        self.assertEqual(result["disable"]["unregister"], ["memory"])

    def test_link_enable_and_disable_have_empty_patch_plans(self):
        program = prepare_program(ALLOCATION_ONLY, "Target.exe")
        memory = Memory()
        allocations = {"memory": {"address": 0x10000, "size": 256}}
        enable = link_program(program, memory, allocations=allocations, assembler=self.assembler)
        self.assertEqual(enable["blocks"], [])
        # The empty-sections return carries no block plan; allocation
        # requests reach the engine through preflight_program, which
        # test_preflight_requests_the_owned_allocation covers.
        self.assertEqual(enable["allocation_requests"], [])
        disable = link_program(program, memory, allocations=allocations, phase="disable", assembler=self.assembler)
        self.assertEqual(disable["blocks"], [])
        self.assertEqual(disable["deallocations"], ["memory"])
        self.assertEqual(disable["unregister"], ["memory"])


class DirectiveGrammarTests(unittest.TestCase):
    """WP-31: 2-arg dealloc, registerlabel, fullaccess no-op."""

    def test_dealloc_one_and_two_arg_forms(self):
        one = prepare_program("[ENABLE]\nalloc(memory,0x100)\n[DISABLE]\ndealloc(memory)", "Target.exe")
        self.assertEqual(next(node for node in one["disable"] if node["op"] == "dealloc"),
                         {"op": "dealloc", "symbols": ["memory"]})
        two = prepare_program("[ENABLE]\nalloc(memory,0x100)\n[DISABLE]\ndealloc(memory,0x100)", "Target.exe")
        self.assertEqual(next(node for node in two["disable"] if node["op"] == "dealloc"),
                         {"op": "dealloc", "symbols": ["memory"], "size": 256})

    def test_dealloc_size_rejections(self):
        for line, needle in (("dealloc(memory,0)", "dealloc size must contain"),
                             ("dealloc(memory,zz)", "dealloc size must contain"),
                             ("dealloc(memory,0x100001)", "dealloc size must contain"),
                             ("dealloc(memory,100,10)", "dealloc requires one symbol"),
                             ("dealloc(*,100)", "Wildcard dealloc takes no size.")):
            with self.subTest(line=line), self.assertRaisesRegex(ProgramError, needle):
                prepare_program(f"[ENABLE]\nalloc(memory,0x100)\n[DISABLE]\n{line}", "Target.exe")

    def test_registerlabel_owned_positional_label(self):
        program = prepare_program("[ENABLE]\nalloc(cave,0x100)\ncave:\nflag:\ndb 0\n"
                                  "registerlabel(flag)\n[DISABLE]\ndealloc(*)\nunregistersymbol(flag)", "Target.exe")
        self.assertEqual(program["provides"], ["flag"])

    def test_registerlabel_unowned_symbol_refused(self):
        with self.assertRaisesRegex(ProgramError, "Cannot register a symbol not owned by this program: unknown."):
            prepare_program("[ENABLE]\nalloc(cave,0x100)\ncave:\ndb 0\n"
                            "registerlabel(unknown)\n[DISABLE]\ndealloc(*)", "Target.exe")

    def test_fullaccess_accepted_as_bounded_noop(self):
        program = prepare_program("[ENABLE]\n1000:\ndb 90\nfullaccess(1000, 0x1000)\n[DISABLE]\n1000:\ndb 00",
                                  "Target.exe")
        self.assertIn("fullaccess", program["capabilities"])
        self.assertEqual(next(node for node in program["enable"] if node["op"] == "fullaccess"),
                         {"op": "fullaccess", "address": "1000", "size": 4096})

    def test_fullaccess_rejections(self):
        for line, needle in (("fullaccess(1000)", "fullaccess requires an address expression and a byte size."),
                             ("fullaccess(1000, 0)", "fullaccess size must contain"),
                             ("fullaccess(1000, 0x1000001)", "fullaccess size must contain")):
            with self.subTest(line=line), self.assertRaisesRegex(ProgramError, needle):
                prepare_program(f"[ENABLE]\n1000:\ndb 90\n{line}\n[DISABLE]\n1000:\ndb 00", "Target.exe")


class ReserveDirectiveTests(unittest.TestCase):
    """WP-35: operand-less dq/resb reservations inside owned allocations."""

    def test_bare_dq_inside_alloc_is_reserve_node(self):
        program = prepare_program("[ENABLE]\nalloc(memory,0x100)\ncave:\ndq\ndb 0\n[DISABLE]\ndealloc(*)", "Target.exe")
        self.assertEqual(next(node for node in program["enable"] if node["op"] == "reserve"),
                         {"op": "reserve", "directive": "dq", "bytes": 8})

    def test_resb_count_inside_alloc(self):
        program = prepare_program("[ENABLE]\nalloc(memory,0x100)\ncave:\nresb 5\n[DISABLE]\ndealloc(*)", "Target.exe")
        self.assertEqual(next(node for node in program["enable"] if node["op"] == "reserve"),
                         {"op": "reserve", "directive": "resb", "bytes": 5})

    def test_reserve_outside_owned_allocation_refused(self):
        for line in ("dq", "resb 4"):
            with self.subTest(line=line), self.assertRaisesRegex(ProgramError,
                                                                "Uninitialized reservation \\(dq/resb\\) requires a program-owned allocation."):
                prepare_program(f"[ENABLE]\n1000:\n{line}\n[DISABLE]\n1000:\ndb 00", "Target.exe")

    def test_resb_count_rejections(self):
        for line in ("resb 0", "resb zz", "resb 0x100001"):
            with self.subTest(line=line), self.assertRaisesRegex(ProgramError, "resb count must contain"):
                prepare_program(f"[ENABLE]\nalloc(memory,0x100)\ncave:\n{line}\n[DISABLE]\ndealloc(*)", "Target.exe")

    def test_dq_with_operands_stays_a_data_node(self):
        program = prepare_program("[ENABLE]\nalloc(memory,0x100)\ncave:\ndq 0\n[DISABLE]\ndealloc(*)", "Target.exe")
        self.assertEqual([node["op"] for node in program["enable"]], ["alloc", "cursor", "data"])

    def test_reserve_counts_toward_the_generated_byte_bound(self):
        # 3 * resb(0x100000) + resb(#1048568) == 4194296 generated bytes.
        # A bare dq on top lands exactly on MAX_TOTAL_BYTES, proving the
        # bare dq counts exactly 8; one further resb 1 overflows the bound.
        from ct2trainer.native.aa_program import MAX_BLOCK_BYTES, MAX_TOTAL_BYTES
        self.assertEqual(3 * MAX_BLOCK_BYTES + 1048568 + 8, MAX_TOTAL_BYTES,
                         "test arithmetic drift: bare dq must count exactly 8 bytes")
        filler = "resb 0x100000\n" * 3 + "resb #1048568\n"
        program = prepare_program("[ENABLE]\nalloc(memory,0x100000)\ncave:\n" + filler
                                  + "dq\n[DISABLE]\ndealloc(*)", "Target.exe")
        self.assertTrue(program["allocation_writable"]["memory"])
        with self.assertRaisesRegex(ProgramError, "generated-byte"):
            prepare_program("[ENABLE]\nalloc(memory,0x100000)\ncave:\n" + filler
                            + "dq\nresb 1\n[DISABLE]\ndealloc(*)", "Target.exe")


class NewDirectiveLinkTests(unittest.TestCase):
    """WP-29/31/35 link-level byte-exact behavior (pinned NASM)."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.assembler = NasmAssembler()
        except AssemblyError as exc:
            raise unittest.SkipTest(str(exc))

    def test_reserve_emits_zero_filled_bytes_byte_exact(self):
        for source, expected in (("[ENABLE]\nalloc(cave,0x10)\ncave:\ndq\n[DISABLE]\ndealloc(*)", "00" * 8),
                                 ("[ENABLE]\nalloc(cave,0x10)\ncave:\nresb 5\n[DISABLE]\ndealloc(*)", "00" * 5)):
            with self.subTest(expected=expected):
                program = prepare_program(source, "Target.exe")
                linked = link_program(program, Memory(),
                                      allocations={"cave": {"address": 0x10000, "size": 16,
                                                            "executable": False, "writable": True}},
                                      assembler=self.assembler)
                self.assertEqual(linked["blocks"][0]["bytes"], expected)

    def test_fullaccess_is_never_emitted_to_nasm(self):
        program = prepare_program("[ENABLE]\n1000:\ndb 90\nfullaccess(1000, 0x1000)\n[DISABLE]\n1000:\ndb 00",
                                  "Target.exe")
        linked = link_program(program, Memory(), assembler=self.assembler)
        self.assertEqual(linked["blocks"][0]["bytes"], "90")
        self.assertNotIn("fullaccess", linked["nasm_source"])


if __name__ == "__main__":
    unittest.main()
