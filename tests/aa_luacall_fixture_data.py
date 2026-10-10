# -*- coding: utf-8 -*-
"""Hand-verified fixture data for the pinned AA luaCall plan model.

No TableReferences, no CE inputs.  Every program below is a synthetic byte
form in the style of the pinned corpus pattern
``luaCall(lua_aobscan("AOB","<mod>.exe","EB ** ..."))`` (re2 / Alien
Isolation / Borderlands 3 shapes); expected values are pinned literals,
never recomputed at test time.
"""

# --- whole programs (analyze_luacall_program) -------------------------------

AOB_TWO_PHASE = (
    '[ENABLE]\n'
    'luaCall(lua_aobscan("healthAnchor", "re2.exe", "EB ** ** 75"))\n'
    'healthAnchor:\n'
    'dd 0FFFFFFF\n'
    '[DISABLE]\n'
    'luaCall(lua_aobscan("healthAnchor", "re2.exe", "EB ** ** 75"))\n'
    'healthAnchor:\n'
    'dd 00000001\n'
)

AOB_ONE_SHOT = (
    '[ENABLE]\n'
    'luaCall(lua_aobscan("spawnPoint", "game.exe", "48 8B ?? 75 **"))\n'
    'spawnPoint:\n'
    'db 90\n'
)

NTH_AOB_CALL = (
    '[ENABLE]\n'
    'luaCall(ct2trainerNthAOB("nthAnchor", "mod.exe", "EB 90 90", 2))\n'
    'nthAnchor:\n'
    'db 01\n'
    '[DISABLE]\n'
    'luaCall(ct2trainerNthAOB("nthAnchor", "mod.exe", "EB 90 90", 2))\n'
    'nthAnchor:\n'
    'db 90\n'
)

GENERIC_CALLS = (
    '[ENABLE]\n'
    'luaCall(setValue("speed", 2))\n'
    'db 01\n'
    "luaCall(flag_on('manual'))\n"
    '[DISABLE]\n'
    'luaCall(setValue("speed", 0))\n'
)

PREAMBLE_CALL = (
    'luaCall(init("boot"))\n'
    '[ENABLE]\n'
    'db 01\n'
    '[DISABLE]\n'
    'db 00\n'
)

COMMENTED_CALLS = (
    '// luaCall(fake())\n'
    '[ENABLE]\n'
    '/* block\n'
    'luaCall(fake2("x"))\n'
    '*/\n'
    'db 01\n'
    '[DISABLE]\n'
    'db 00\n'
)

# --- refused whole programs --------------------------------------------------

BAD_UNBALANCED = (
    '[ENABLE]\n'
    'luaCall(lua_aobscan("a", "m.exe", "EB")\n'
    '[DISABLE]\n'
)

BAD_TRAILING = (
    '[ENABLE]\n'
    'luaCall(x()) db 01\n'
    '[DISABLE]\n'
)

BAD_MULTI_LINE = (
    '[ENABLE]\n'
    'luaCall(a(\n'
    '1))\n'
    '[DISABLE]\n'
)

BAD_UNTERMINATED_STRING = (
    '[ENABLE]\n'
    'luaCall(a("abc))\n'
    '[DISABLE]\n'
)

BAD_BAD_EXPRESSION = (
    '[ENABLE]\n'
    'luaCall(x(1,))\n'
    '[DISABLE]\n'
)

BAD_MODE_SECTION = (
    '[ENABLE]\n'
    '{$lua}\n'
    'return nil\n'
    '{$asm}\n'
    '[DISABLE]\n'
)

BAD_NO_PHASES = 'luaCall(x())\n'

BAD_PHASE_ORDER = (
    '[DISABLE]\n'
    '[ENABLE]\n'
)

BAD_DUPLICATE_PHASE = (
    '[ENABLE]\n'
    '[ENABLE]\n'
    '[DISABLE]\n'
)

BAD_SYMBOL_CONFLICT = (
    '[ENABLE]\n'
    'luaCall(lua_aobscan("sym", "m.exe", "EB"))\n'
    'luaCall(lua_aobscan("sym", "m.exe", "90"))\n'
    '[DISABLE]\n'
)

BAD_AOB_ARG_COUNT = (
    '[ENABLE]\n'
    'luaCall(lua_aobscan("aob", "m.exe"))\n'
    '[DISABLE]\n'
)

BAD_AOB_NONSTRING_MODULE = (
    '[ENABLE]\n'
    'luaCall(lua_aobscan("aob", 5, "EB"))\n'
    '[DISABLE]\n'
)

BAD_AOB_MODULE = (
    '[ENABLE]\n'
    'luaCall(lua_aobscan("aob", "m", "EB"))\n'
    '[DISABLE]\n'
)

BAD_AOB_ALL_WILDCARD = (
    '[ENABLE]\n'
    'luaCall(lua_aobscan("aob", "m.exe", "** **"))\n'
    '[DISABLE]\n'
)

BAD_AOB_OCCURRENCE_ZERO = (
    '[ENABLE]\n'
    'luaCall(ct2trainerNthAOB("aob", "m.exe", "EB", 0))\n'
    '[DISABLE]\n'
)

BAD_AOB_OCCURRENCE_HUGE = (
    '[ENABLE]\n'
    'luaCall(ct2trainerNthAOB("aob", "m.exe", "EB", 65537))\n'
    '[DISABLE]\n'
)

BAD_AOB_SYMBOL_ALL_HEX = (
    '[ENABLE]\n'
    'luaCall(lua_aobscan("ABC", "m.exe", "EB"))\n'
    '[DISABLE]\n'
)

# --- expression-level fixtures (parse_luacall) ------------------------------

EXPR_VALID = (
    'lua_aobscan("sym", "mod.exe", "EB **")',
    'ct2trainerNthAOB("nth", "mod.exe", "48 8B ??", 3)',
    "setValue('speed', 2)",
    'flag_on(manual)',
    'noop()',
    'a(  1 ,  2 )',
    'x("say \\"hi\\"")',
    'x("tab\\there")',
    'x("back\\\\slash")',
)

EXPR_INVALID = (
    '',
    '   ',
    'x',
    '1x(1)',
    'x(1,)',
    'x(1 2)',
    'x(a())',
    'x("bad\\z")',
    'x("unterminated',
    'x(;1)',
    'x(1))',
    'x(1;2)',
)

EXPR_NON_STR = (7, None, b'x(1)', ['x(1)'], {'x': 1})
