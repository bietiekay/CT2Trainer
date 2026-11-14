"""RT-4.5 (O15/O22/O24/O25) named-refusal pins.

compile_table-level pins for the exact refusal strings of the AA
directive/script coverage lane:

- O15: ``usemono()`` targets a Cheat Engine newer than 7.5; out of parity
  scope (both halves named, the native half carries the exact line number).
- O22: createThread()/threadWait() are gated in the native staged runtime
  (no thread backend ships); the static half names the unsupported
  directive first (Witcher3 id 192 shape).
- O24: assert argument-count validation of the static AA envelope of a
  Lua record (Cyberpunk 159 shape).
- O25: the unterminated source block comment is a CE 7.5 comment-to-EOF
  parity (autoassembler.pas removecomments L732-798, read-only reference:
  the comment state persists to the end of the source, there is no error
  path) — the Sonic 1337230409 shape (valid program + trailing
  unterminated brace comment) loads, while a comment that swallows a
  section marker removes that section, so the section contract still
  applies with its own named refusal.

Self-contained synthetic CT; no TableReferences, no CE inputs.
"""
import tempfile
import unittest
import xml.sax.saxutils
from pathlib import Path

from ct2trainer.native.compiler import compile_table


PROCESS = "FixtureTarget.exe"


def escape(script: str) -> str:
    return xml.sax.saxutils.escape(script)


def record(entry_id: int, label: str, script: str) -> str:
    return (f'<CheatEntry><ID>{entry_id}</ID><Description>{label}</Description>'
            f'<VariableType>Auto Assembler Script</VariableType>'
            f'<AssemblerScript>{escape(script)}</AssemblerScript></CheatEntry>')


def table_xml(body: str) -> str:
    return ('<CheatTable CheatEngineTableVersion="45"><LuaScript></LuaScript>'
            '<CheatEntries>' + body + '</CheatEntries></CheatTable>')


USEMONO_SCRIPT = (
    "[ENABLE]\n"
    "assert(FixtureTarget.exe+0x10,00)\n"
    "usemono()\n"
    "FixtureTarget.exe+0x10:\n"
    "db 01\n"
    "[DISABLE]\n"
    "FixtureTarget.exe+0x10:\n"
    "db 00\n"
)

CREATE_THREAD_SCRIPT = (
    "[ENABLE]\n"
    "createThread(handler)\n"
    "[DISABLE]\n"
)

ASSERT_ARGCOUNT_SCRIPT = (
    "[ENABLE]\n"
    "{$lua}\n"
    "return nil\n"
    "{$asm}\n"
    "assert(true)\n"
    "FixtureTarget.exe+0x10:\n"
    "db 01\n"
    "[DISABLE]\n"
    "FixtureTarget.exe+0x10:\n"
    "db 00\n"
)

# O25 (SonicFrontiers 1337230409 shape, 0.50 CE parity re-pin): the
# complete program comes first; the trailing brace comment that never
# closes is stripped to the end of the source, exactly like CE 7.5
# removecomments does, so the record loads.
TRAILING_UNCLOSED_COMMENT_SCRIPT = (
    "[ENABLE]\n"
    "FixtureTarget.exe+0x10:\n"
    "db 01\n"
    "[DISABLE]\n"
    "FixtureTarget.exe+0x10:\n"
    "db 00\n"
    "{\n"
    "// ORIGINAL CODE - INJECTION POINT (unterminated by design)\n"
)

# The same parity seen from the section contract: a block comment that
# opens before [DISABLE] and never closes swallows the marker, so the
# stripped program loses its disable section and the named section
# refusal fires instead of a comment refusal.
COMMENT_SWALLOWS_DISABLE_SCRIPT = (
    "[ENABLE]\n"
    "/* this comment never closes\n"
    "assert(FixtureTarget.exe+0x10,00)\n"
    "FixtureTarget.exe+0x10:\n"
    "db 01\n"
    "[DISABLE]\n"
    "FixtureTarget.exe+0x10:\n"
    "db 00\n"
)


class NamedRefusalTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "refusals.CT"
        self.path.write_text(
            table_xml(record(100, '"usemono"', USEMONO_SCRIPT)
                      + record(101, '"createthread"', CREATE_THREAD_SCRIPT)
                      + record(102, '"assert argcount"', ASSERT_ARGCOUNT_SCRIPT)
                      + record(103, '"trailing unclosed comment"',
                              TRAILING_UNCLOSED_COMMENT_SCRIPT)
                      + record(104, '"comment swallows DISABLE"',
                              COMMENT_SWALLOWS_DISABLE_SCRIPT)),
            encoding="utf-8")
        self.plan = compile_table(self.path, PROCESS)

    def _entry(self, entry_id: int) -> dict:
        return next(e for e in self.plan["entries"] if e["id"] == entry_id)

    def test_usemono_is_refused_named_in_both_halves(self):
        entry = self._entry(100)
        self.assertFalse(entry["supported"])
        self.assertEqual(
            entry["reason"],
            "usemono targets a Cheat Engine newer than 7.5; out of parity scope. "
            "Native assembly: Line 3: usemono targets a Cheat Engine newer than "
            "7.5; out of parity scope.")

    def test_createthread_is_gated_in_the_native_staged_runtime(self):
        entry = self._entry(101)
        self.assertFalse(entry["supported"])
        self.assertEqual(
            entry["reason"],
            "Unsupported AA directive: createthread. Native assembly: "
            "createThread()/threadWait() are gated in the native staged "
            "runtime: no thread backend is part of the shipped trainer profile.")

    def test_assert_argument_count_is_refused_named(self):
        entry = self._entry(102)
        self.assertFalse(entry["supported"])
        self.assertEqual(
            entry["reason"],
            "Static AA envelope: Line 2: assert has an invalid argument count.")

    def test_trailing_unterminated_block_comment_is_comment_to_eof(self):
        # CE 7.5 parity: the unterminated brace comment at the end of the
        # source is stripped to EOF, so the complete program before it
        # loads (SonicFrontiers 1337230409 "Pin Ball" shape).
        entry = self._entry(103)
        self.assertTrue(entry["supported"])

    def test_comment_that_swallows_the_disable_marker_is_a_section_refusal(self):
        # The same parity from the section contract: the comment-to-EOF
        # strip removes the swallowed [DISABLE] marker, so the program
        # loses its disable section and the named section refusal fires
        # (no comment refusal any more).
        entry = self._entry(104)
        self.assertFalse(entry["supported"])
        self.assertEqual(
            entry["reason"],
            "Both ENABLE and DISABLE sections are required. "
            "Native assembly: Program requires explicit ENABLE and "
            "DISABLE sections.")


if __name__ == '__main__':
    unittest.main()
