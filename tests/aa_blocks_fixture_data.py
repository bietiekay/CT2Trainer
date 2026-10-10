# -*- coding: utf-8 -*-
"""Hand-verified fixture data for the pinned AA block models.

No TableReferences, no CE inputs: every program below is synthetic;
expected values are pinned literals, never recomputed at test time.
"""

# --- conditional fixtures (prune_conditionals) --------------------------------

CONDITIONAL_TRUE = (
    "[ENABLE]\n"
    "{$if DEBUG=1}\n"
    "db 01\n"
    "{$endif}\n"
    "db 02\n"
    "[DISABLE]\n"
    "db 00\n"
)

CONDITIONAL_ELSE = (
    "[ENABLE]\n"
    "{$if MODE=2}\n"
    "db 01\n"
    "{$else}\n"
    "db 02\n"
    "{$endif}\n"
)

NESTED_TRUE = (
    "[ENABLE]\n"
    "{$if A=1}\n"
    "{$if B=1}\n"
    "{$if C=1}\n"
    "db 0A\n"
    "{$endif}\n"
    "{$else}\n"
    "db 0B\n"
    "{$endif}\n"
    "{$endif}\n"
)

NESTED_INNER_ELSE = (
    "[ENABLE]\n"
    "{$if A=1}\n"
    "{$if B=0}\n"
    "db 0A\n"
    "{$else}\n"
    "db 0B\n"
    "{$endif}\n"
    "{$endif}\n"
)

DEFINE_NAME_RHS = (
    "{$if A=B}\n"
    "db 01\n"
    "{$endif}\n"
)

HEX_LITERAL = (
    "{$if A=$FF}\n"
    "db 01\n"
    "{$endif}\n"
)

NEGATIVE_LITERAL = (
    "{$if A=-1}\n"
    "db 01\n"
    "{$endif}\n"
)

CASE_INSENSITIVE = (
    "{$IF DEBUG=1}\n"
    "db 01\n"
    "{$ELSE}\n"
    "db 02\n"
    "{$ENDIF}\n"
)

UNDEFINED_DEFINE = (
    "{$if MISSING=1}\n"
    "db 01\n"
    "{$endif}\n"
)

UNSUPPORTED_EXPR = (
    "{$if A < 1}\n"
    "db 01\n"
    "{$endif}\n"
)

UNCLOSED_IF = (
    "[ENABLE]\n"
    "{$if DEBUG=1}\n"
    "db 01\n"
    "[DISABLE]\n"
    "db 00\n"
)

ORPHAN_ELSE = (
    "[ENABLE]\n"
    "db 01\n"
    "{$else}\n"
    "[DISABLE]\n"
    "db 00\n"
)

ORPHAN_ENDIF = (
    "[ENABLE]\n"
    "db 01\n"
    "{$endif}\n"
    "[DISABLE]\n"
    "db 00\n"
)

DOUBLE_ELSE = (
    "{$if A=1}\n"
    "db 01\n"
    "{$else}\n"
    "db 02\n"
    "{$else}\n"
    "db 03\n"
    "{$endif}\n"
)


def depth_program(depth):
    """A program with ``depth`` nested ``{$if A=1}`` blocks around ``db 01``."""
    return ("".join("{$if A=1}\n" for _ in range(depth))
            + "db 01\n"
            + "".join("{$endif}\n" for _ in range(depth)))


# --- nested-assembly fixtures (resolve_nested_assembly) ------------------------

LABELS_CHAIN = (
    "first:\n"
    "db 01\n"
    'autoassemble("second")\n'
    "second:\n"
    "db 02\n"
    'autoasm("third")\n'
    "third:\n"
    "db 03\n"
)

CALLS_EXTERNAL = (
    "patch:\n"
    'autoassemble("sharedHelper")\n'
    "db 01\n"
)

EXTERNAL_SHARED = "sharedHelper:\ndb 09\n"

COLLISION_INTERNAL = "sharedHelper:\ndb 01\n"

DUP_INVOKE = (
    'autoassemble("helper")\n'
    "helper:\n"
    "db 01\n"
    'autoassemble("helper")\n'
)

DUP_DEFINE = (
    "helper:\n"
    "db 01\n"
    "helper:\n"
    "db 02\n"
)

CYCLE = (
    "a:\n"
    'autoassemble("b")\n'
    "b:\n"
    'autoassemble("a")\n'
)

SELF_CYCLE = (
    "a:\n"
    'autoassemble("a")\n'
)

UNKNOWN_LABEL = 'autoassemble("missing")\n'

DEAD_BODY_UNKNOWN = (
    "unused:\n"
    'autoassemble("ghost")\n'
    "main:\n"
    "db 01\n"
)

# --- analyze_blocks fixtures ----------------------------------------------------

COMBINED_ANALYZE = (
    "[ENABLE]\n"
    "{$if PATCH=1}\n"
    "first:\n"
    'autoassemble("second")\n'
    "second:\n"
    "db 02\n"
    "{$endif}\n"
    "db 03\n"
)

# ``analyze_blocks(REMAP, defines={'X': 1})`` keeps the call (error);
# ``analyze_blocks(REMAP, defines={'X': 0})`` prunes it (no error).
REMAP = (
    "[ENABLE]\n"
    "{$if X=1}\n"
    'autoassemble("ghost")\n'
    "{$endif}\n"
)
