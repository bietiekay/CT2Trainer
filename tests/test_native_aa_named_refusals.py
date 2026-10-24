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
- O25: unterminated source block comment (Sonic 1337230409 shape).

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

UNCLOSED_COMMENT_SCRIPT = (
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
                      + record(103, '"unclosed comment"', UNCLOSED_COMMENT_SCRIPT)),
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

    def test_unterminated_block_comment_is_refused_named(self):
        entry = self._entry(103)
        self.assertFalse(entry["supported"])
        self.assertEqual(entry["reason"], "Unterminated source block comment.")


if __name__ == '__main__':
    unittest.main()
