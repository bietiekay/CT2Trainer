"""WP-26 Lua dialect: no-op directives, in-block phase markers, one-shot rules.

Reference-corpus gap families closed by this module (corpus shapes mirrored
as own synthetic fixtures; the 151-table reference corpus stays read-only
and local):

- D1 ``Lua/ASM delimiters must occupy standalone lines`` (106 entries):
  CE no-op directives (``{$strict}``/``{$ccode}``/``{$luacode}``/
  ``{$try}``/``{$except}`` plus a stray ``{$asm}``) are stripped; any other
  well-formed ``{$...}`` token raises the precise named
  ``Non-profile {$...} directive: <name>`` error in both the plain AA and
  the Lua paths.
- D2 ``Lua program phases are duplicated or out of order`` (54 entries):
  a fresh ``[ENABLE]``/``[DISABLE]`` transition inside an explicit
  ``{$lua}`` chunk is a structural phase boundary; pre-``[ENABLE]`` text is
  the shared preamble of both phases.  A phase-appearing line that is not
  a fresh transition keeps its legacy Lua-body meaning in explicitly
  closed chunks (open-ended chunks stay fail-closed).
- D3 ``ASM delimiter without a Lua section`` (7 entries): a redundant
  ``{$asm}`` in the AA context outside any Lua section is a no-op.
"""
import re
import tempfile
import unittest
from pathlib import Path

from ct2trainer.native.compiler import (compile_table,
                                        validate_plan as validate_compiler_plan)
from ct2trainer.native.engine import (validate_plan as validate_engine_plan)
from ct2trainer.native.lua_program import (LuaProgramError, has_lua_sections,
                                           phase_expansion,
                                           prepare_lua_program)

PROCESS = "FixtureTarget.exe"

# A known-valid two-phase static envelope (plain cursor + data, no symbols).
ANCHORS = ("[ENABLE]\n"
           "FixtureTarget.exe+40:\n"
           "db 01\n"
           "[DISABLE]\n"
           "FixtureTarget.exe+40:\n"
           "db 00")


class RecordingHost:
    def __init__(self, results=None):
        self.results = results or {}
        self.calls = []
        self.checks = []

    def execute(self, source, *, syntaxcheck=False):
        self.calls.append((source, syntaxcheck))
        return self.results.get(source)

    def check_sources(self, sources):
        self.checks.append(sources)
        return [self.execute(source, syntaxcheck=True) for source in sources]


def ct_body(*scripts):
    entries = "".join(
        '<CheatEntry><ID>%d</ID><Description>"wp26 %d"</Description>'
        '<VariableType>Auto Assembler Script</VariableType>'
        '<AssemblerScript>%s</AssemblerScript></CheatEntry>'
        % (index + 1, index + 1, script)
        for index, script in enumerate(scripts))
    return ('<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
            + entries + '</CheatEntries></CheatTable>')


class NoopDirectiveTests(unittest.TestCase):
    """D1/D3: CE no-op directives are stripped; unknowns get precise names."""

    NOOP = ("{$asm}", "{$STRICT}", "{$ccode}", "{$luacode}",
            "{$try}", "{$except}")

    def test_routing_and_parse_accept_noops_in_lua_path(self):
        for line in self.NOOP:
            with self.subTest(line=line):
                source = line + "\n" + "{$lua}\nbody()\n{$asm}\n" + ANCHORS
                self.assertTrue(has_lua_sections(source))
                program = prepare_lua_program(source, PROCESS)
                self.assertEqual(program["static_source"], ANCHORS)

    def test_stray_asm_between_aa_blocks_is_a_noop(self):
        # D3 corpus shape: a redundant {$asm} in the AA context after a Lua
        # section has closed (between two AA blocks) is stripped.
        source = ("{$lua}\nP()\n{$asm}\n"
                  "[ENABLE]\nFixtureTarget.exe+40:\ndb 01\n"
                  "{$asm}\n"
                  "db 02\n"
                  "[DISABLE]\nFixtureTarget.exe+40:\ndb 00\n")
        program = prepare_lua_program(source, PROCESS)
        self.assertEqual(program["static_source"],
                         "[ENABLE]\nFixtureTarget.exe+40:\ndb 01\n"
                         "db 02\n[DISABLE]\nFixtureTarget.exe+40:\ndb 00")
        self.assertFalse(program["one_shot"])

    def test_unknown_directive_raises_the_precise_name(self):
        cases = {"{$bogus}": "bogus",
                 "{$alloc(x,10)}": "alloc(x,10)",
                 "{$undefine A}": "undefine A"}
        for line, name in cases.items():
            pattern = ("Non-profile \\{\\$...\\} directive: "
                       + re.escape(name))
            with self.subTest(line=line):
                with self.assertRaisesRegex(LuaProgramError, pattern):
                    has_lua_sections(line + "\n" + "{$lua}\nbody()\n" + ANCHORS)
                with self.assertRaisesRegex(LuaProgramError, pattern):
                    prepare_lua_program(line + "\n" + "{$lua}\nbody()\n"
                                         + ANCHORS, PROCESS)

    def test_unterminated_directive_keeps_the_standalone_error(self):
        source = "{$broken\n" + "{$lua}\nbody()\n{$asm}\n" + ANCHORS
        with self.assertRaisesRegex(
                LuaProgramError,
                "Lua/ASM delimiters must occupy standalone lines"):
            has_lua_sections(source)


class InBlockPhaseMarkerTests(unittest.TestCase):
    """D2: fresh in-block [ENABLE]/[DISABLE] transitions are structural."""

    def test_explicit_chunk_markers_split_phases(self):
        # Corpus shape (examples-D2.json): preamble syntaxcheck guard,
        # in-block [ENABLE], Lua body, {$asm}, stray AA, [DISABLE] with a
        # contentless disable Lua chunk.
        source = ("{$LUA}\n"
                  "if syntaxcheck then return end\n"
                  "[ENABLE]\n"
                  "\n"
                  "local msg = [[\nGame\n]]\n"
                  "mShowMessage('Informations', msg, false, 0)\n"
                  "{$asm}\n"
                  "nop\n"
                  "\n"
                  "[DISABLE]\n")
        program = prepare_lua_program(source, PROCESS)
        self.assertTrue(program["one_shot"])
        host = RecordingHost()
        phase_expansion(host, program, "enable")
        self.assertEqual(host.calls, [
            ("if syntaxcheck then return end\n"
             "\nlocal msg = [[\nGame\n]]\n"
             "mShowMessage('Informations', msg, false, 0)", False)])
        disable_host = RecordingHost()
        phase_expansion(disable_host, program, "disable")
        self.assertEqual(
            disable_host.calls,
            [("if syntaxcheck then return end\n", False)])

    def test_open_chunk_markers_stay_structural(self):
        # Open-ended single chunk with both markers inside: the preamble is
        # shared and each phase chunk receives it.
        source = "{$lua}\nP()\n[ENABLE]\nE()\n[DISABLE]\nD()"
        program = prepare_lua_program(source, PROCESS)
        self.assertFalse(program["one_shot"])
        host = RecordingHost()
        phase_expansion(host, program, "enable")
        self.assertEqual(host.calls, [("P()\nE()", False)])
        disable_host = RecordingHost()
        phase_expansion(disable_host, program, "disable")
        self.assertEqual(disable_host.calls, [("P()\nD()", False)])

    def test_duplicate_enable_in_open_chunk_still_refused(self):
        source = ("{$lua}\nP()\n[ENABLE]\nE()\n[ENABLE]\nX()\n"
                  "[DISABLE]\nD()")
        with self.assertRaisesRegex(LuaProgramError,
                                    "phases are duplicated or out of order"):
            prepare_lua_program(source, PROCESS)

    def test_disable_before_enable_in_open_chunk_still_refused(self):
        with self.assertRaisesRegex(LuaProgramError,
                                    "phases are duplicated or out of order"):
            prepare_lua_program("{$lua}\n[DISABLE]\nD()\n[ENABLE]\nE()",
                                PROCESS)

    def test_nonfresh_marker_in_closed_chunk_stays_lua_body(self):
        # Legacy contract: a phase-appearing line that is not a fresh
        # transition remains Lua data in an explicitly closed chunk
        # (pinned by test_native_lua_program).
        source = ("{$lua}\nP()\n[ENABLE]\nE()\n[ENABLE]\nX()\n"
                  "{$asm}\nFixtureTarget.exe+40:\ndb 01\n[DISABLE]\n"
                  "FixtureTarget.exe+40:\ndb 00\n")
        program = prepare_lua_program(source, PROCESS)
        host = RecordingHost()
        phase_expansion(host, program, "enable")
        self.assertEqual(host.calls, [("P()\nE()\n[ENABLE]\nX()", False)])

    def test_unterminated_lua_string_still_refused(self):
        with self.assertRaisesRegex(LuaProgramError,
                                    "Unterminated Lua section"):
            prepare_lua_program("{$lua}\nP()\n[ENABLE]\nE()\n[[\n", PROCESS)

    def test_top_level_chunk_shape_unchanged(self):
        # Pinned shape: chunks closed before any in-block marker keep the
        # preamble as its own non-shared chunk in both phase expansions.
        source = ("{$lua}\npreamble()\n{$asm}\n"
                  "[ENABLE]\n{$lua}\nenable()\n{$asm}\n"
                  "FixtureTarget.exe+40:\ndb 01\n"
                  "[DISABLE]\n{$lua}\ndisable()\n{$asm}\n"
                  "FixtureTarget.exe+40:\ndb 00\n")
        program = prepare_lua_program(source, PROCESS)
        host = RecordingHost()
        phase_expansion(host, program, "enable")
        self.assertEqual(host.calls,
                         [("preamble()", False), ("enable()", False)])
        disable_host = RecordingHost()
        phase_expansion(disable_host, program, "disable")
        self.assertEqual(disable_host.calls,
                         [("preamble()", False), ("disable()", False)])


class OneShotEmptyDisableTests(unittest.TestCase):
    """A contentless disable Lua chunk must not defeat one_shot."""

    def test_empty_disable_lua_chunk_keeps_one_shot(self):
        # [DISABLE] opens an explicit empty Lua chunk ({$lua} immediately
        # closed by {$asm}); contentless disable must not defeat one_shot.
        source = ("{$lua}\nP()\n[ENABLE]\nE()\n{$asm}\nnop\n"
                  "[DISABLE]\n{$lua}\n{$asm}\n")
        self.assertTrue(prepare_lua_program(source, PROCESS)["one_shot"])

    def test_disable_content_keeps_two_phase(self):
        source = ("{$lua}\nP()\n{$asm}\n"
                  "[ENABLE]\nFixtureTarget.exe+40:\ndb 01\n"
                  "[DISABLE]\n{$lua}\nD()\n{$asm}\n"
                  "FixtureTarget.exe+40:\ndb 00\n")
        self.assertFalse(prepare_lua_program(source, PROCESS)["one_shot"])

    def test_pure_lua_enable_only_stays_one_shot(self):
        source = "{$lua}\nP()\n[ENABLE]\nE()\n{$asm}\n"
        self.assertTrue(prepare_lua_program(source, PROCESS)["one_shot"])


class CompileWiringTests(unittest.TestCase):
    """Per-record containment through compile_table and both validators."""

    def compile(self, *scripts):
        with tempfile.TemporaryDirectory() as directory:
            table = Path(directory) / "directives.ct"
            table.write_text(ct_body(*scripts), encoding="utf-8")
            plan = compile_table(table, PROCESS)
            validate_compiler_plan(plan)
            validate_engine_plan(plan)
            return plan

    def test_unknown_directive_blocks_only_its_record(self):
        good = "{$lua}\nE()\n{$asm}\n" + ANCHORS
        plan = self.compile("{$bogus}\n" + good, good)
        blocked, supported = plan["entries"][0], plan["entries"][1]
        self.assertFalse(blocked["supported"], blocked["reason"])
        self.assertIn("Non-profile {$...} directive: bogus",
                      blocked["reason"])
        self.assertTrue(supported["supported"], supported["reason"])
        self.assertIn("lua_program", supported)

    def test_noop_directive_record_compiles(self):
        source = "{$STRICT}\n{$lua}\nE()\n{$asm}\n" + ANCHORS
        plan = self.compile(source)
        entry = plan["entries"][0]
        self.assertTrue(entry["supported"], entry["reason"])
        self.assertEqual(entry["lua_program"]["static_source"], ANCHORS)

    def test_d2_shape_record_compiles_and_is_one_shot(self):
        source = ("{$LUA}\nif syntaxcheck then return end\n[ENABLE]\n"
                  "E()\n{$asm}\nnop\n[DISABLE]\n")
        plan = self.compile(source)
        entry = plan["entries"][0]
        self.assertTrue(entry["supported"], entry["reason"])
        self.assertTrue(entry["one_shot"], entry["reason"])


if __name__ == "__main__":
    unittest.main()
