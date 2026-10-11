#!/usr/bin/env python3
"""AP-10 corpus lane: shared static CT classification (read-only, stdlib only).

No CT Lua/AA execution. Scripts are classified by explicit static rules and
marked as syntax assumptions. Mirrors the static semantics of the product's
own table model (src/ct2trainer/table.py) without importing product code.
"""
import re
from collections import Counter

SIMPLE_VALUE_TYPES = frozenset({"Byte", "2 Bytes", "4 Bytes", "8 Bytes", "Float", "Double"})
ADVANCED_VALUE_TYPES = frozenset({"Array of byte", "Binary"})
ALL_VALUE_TYPES = SIMPLE_VALUE_TYPES | ADVANCED_VALUE_TYPES
HEX_INTEGER_TYPES = frozenset({"Byte", "2 Bytes", "4 Bytes", "8 Bytes"})

SUPPORTED_AA_DIRECTIVES = frozenset({
    "aobscan", "aobscanmodule", "aobscanchunk", "aobscanregion", "alloc",
    "dealloc", "align",
    "db", "dw", "dd", "dq", "define", "label", "registersymbol",
    "unregistersymbol", "readmem", "reassemble", "globalalloc", "assert",
})
LOCKED_AA_DIRECTIVES = {
    "createthread": "aa_createthread_threadwait",
    "threadwait": "aa_createthread_threadwait",
    "getprocaddress": "aa_target_api_binding",
    "getprocaddressname": "aa_target_api_binding",
    "getmodulehandle": "aa_target_api_binding",
    "disassemble": "aa_debugger_api",
    "autoassemble": "aa_nested_script",
    "protect": "aa_protection_control",
    "unprotect": "aa_protection_control",
    "luacall": "aa_luacall",
}
# Residual directive-like tokens that are instructions/identifiers, not CE AA
# commands (observed in corpus after block-stripping). Kept as a documented
# allow-list so they do not flip records to unknown.
KNOWN_INSTRUCTION_TOKENS = frozenset({
    "add", "addps", "addpd", "addss", "addsd", "adc", "and", "andps", "andpd",
    "bextr", "bsf", "bsr", "bswap", "bt", "bts", "btr", "btc", "call", "cbw",
    "cdqe", "clc", "cld", "clc", "cmove", "cmovne", "cmovz", "cmovnz",
    "cmovg", "cmovge", "cmovl", "cmovle", "cmovb", "cmovbe", "cmova", "cmovae",
    "cmovno", "cmovb", "cmp", "cmpps", "cmppd", "comiss", "comisd", "cpuid",
    "cvtsd2si", "cvtsd2ss", "cvtss2sd", "cvtss2si", "cvtsi2sd", "cvtsi2ss",
    "daa", "das", "dec", "div", "divss", "divsd", "idiv", "emms", "fadd",
    "fcom", "fcomp", "fcomip", "fdiv", "fdivr", "fidiv", "fild", "fist",
    "fistp", "fst", "fstp", "fxch", "hlt", "idiv", "imul", "in", "inc",
    "int3", "int", "iret", "ja", "jae", "jb", "jbe", "jc", "jcxz", "jecxz",
    "jrcxz", "je", "jg", "jge", "jl", "jle", "jne", "jnb", "jnc", "jno",
    "jns", "jnotb", "jnotc", "jz", "jmp", "loop", "loopz", "loopnz",
    "maxsd",
    "maxss", "minsd", "minss", "mul", "mulpd", "mulps", "mulsd", "mulss",
    "neg", "nop", "not", "or", "orps", "orpd", "out", "pause", "pop", "push",
    "pushad", "popad", "pushfq", "popfq", "pushfd", "popfd", "pusha", "popa",
    "rep", "repe", "repne", "ret", "rol", "ror", "sal", "sar", "sbb", "scas",
    "shl", "shr", "shld", "shrd", "sqrtpd", "sqrtss", "sqrtsd", "stc", "std",
    "sub", "subps", "subpd", "subsd", "subss", "test", "ucomiss", "ucomisd",
    "unpcklpd", "unpcklps", "unpckhpd", "unpckhps", "vmovdqu", "vmovss",
    "vmovsd", "vmovups", "vpxor", "vcomiss", "xadd", "xchg", "xlat", "xor",
    "xorb", "xorw", "xord", "xorq", "xorps", "xorpd", "mov", "movs", "movzx",
    "movsx",
    "movsxd", "movapd", "movaps", "movupd", "movups", "movd", "movq",
    "movdqu", "movddup", "movhlps", "movlhps", "movlhps", "movhlpd",
    "movlpd", "movmskpd", "movmskps", "movntdqa", "movss", "movsd", "lea",
    "lock", "leave", "resb", "resw", "resd", "resq", "times", "bswap",
    "syscall", "sysret", "ud2", "int1", "int3", "nopw", "nopd", "stos",
    "cmps", "enter",
})

LUA_API_GAPS = (
    (re.compile(r"\bspeedhack_(?:setSpeed|getSpeed|setMulti|getMulti)\b", re.I), "lua_clock_speed"),
    (re.compile(r"\b(?:executeCodeEx|executeCode)\s*\(", re.I), "lua_typed_target_call"),
    (re.compile(r"\b(?:LaunchMonoDataCollector|getMonoMethod|getMonoField|getMonoAddress|MonoDataCollector)\b"), "lua_managed_runtime"),
    (re.compile(r"\bcreateThread\s*\(", re.I), "lua_worker_thread"),
    (re.compile(r"\b(?:showMessage|showForm|hideForm)\b", re.I), "lua_gui_api"),
    (re.compile(r"\b(?:getProcHandle|OpenProcess|getOpenProcessID)\b", re.I), "lua_process_api"),
    (re.compile(r"\b(?:registerSymbol|unregisterSymbol|getAddressOfSymbol)\b", re.I), "lua_symbol_api"),
    (re.compile(r"\bgetLuaEngine\s*\(", re.I), "lua_ce_engine_api"),
    (re.compile(r"\b(?:attachProcess|detachProcess|debugProcess|isDebuggingProcess)\b", re.I), "lua_debugger_api"),
    (re.compile(r"\bautoAssemble\s*\(", re.I), "lua_dynamic_assembler"),
)

LUA_OPEN = re.compile(r"\{\s*\$lua\s*\}", re.I)
LUA_CLOSE = re.compile(r"\{\s*\$asm\s*\}", re.I)
BLOCK_IF = re.compile(r"\{\s*\$if\b", re.I)
BLOCK_ENDIF = re.compile(r"\{\s*\$endif\s*\}", re.I)
ENABLE_RE = re.compile(r"\[\s*ENABLE\s*\]", re.I)
DISABLE_RE = re.compile(r"\[\s*DISABLE\s*\]", re.I)
MODULE_REF = re.compile(r"[\w\-]+?\.(?:exe|dll)", re.I)
REG64 = re.compile(r"\b(?:rax|rbx|rcx|rdx|rsp|rbp|rsi|rdi|r[8-9]|r[1][0-5]|rip)\b")
SIMD = re.compile(r"\b(?:movss|movsd|movsdq?|mulss|divss|addss|subss|maxss|minss|comiss|comisd|xorps|shufps|vpxor|vmov[ms]?\w*)\b")
REG32 = re.compile(r"\b(?:eax|ebx|ecx|edx|esp|ebp|esi|edi)\b")
