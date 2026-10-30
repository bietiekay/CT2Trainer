"""Field regression: The Sinking City 2 table-load warnings (0.16.1).

The user field test (2026-10-21) loaded TheSinkingCity2.CT (table
version 46, an OpenProcess attach-helper record, an AOB pointer record
and a ShellExecute support-link record).  The table loaded and worked,
but three plan warnings read like failures.  0.16.1 makes them accurate:

* the local CE table-version reference moved 45 -> 46 (v46 is
  field-verified; CE 7.5, the behavior reference, writes 45);
* the {$LUA} warning states that the embedded Lua runs in the
  trainer's built-in Lua runtime (a supported path);
* the external-action warning is split per API: ShellExecute is the
  safe no-op the native trainer performs (WP-56); messageDialog became a
  safe logged no-op in the 0.20 cycle (RT-5 item E) and keeps a review
  flag.

Pure analysis: synthetic tables only, no CE inputs, no process access.
"""

import tempfile
import unittest
import xml.sax.saxutils
from pathlib import Path

from ct2trainer.native.compiler import compile_table

LUA_WARNING_NEW = ("At least one Auto Assembler script contains {$LUA}; the "
                   "embedded Lua runs in the trainer's built-in Lua runtime "
                   "when the record activates.")
LUA_WARNING_OLD = "At least one Auto Assembler script contains {$LUA}."
SHELL_WARNING = ("At least one script calls ShellExecute; the native trainer "
                 "runs it as a safe no-op (no external program or URL is "
                 "launched).")
MSGDLG_WARNING = ("At least one script calls messageDialog; the native "
                  "trainer does not show a dialog - the call is logged as "
                  "a review event and returns 0 (mbOK) as a safe no-op.")
LEGACY_REVIEW_WARNING = ("At least one script invokes a dialog or external "
                         "action and needs review.")


SC2_SHAPE = (
    '<?xml version="1.0" encoding="utf-8"?>\n'
    '<CheatTable CheatEngineTableVersion="46">\n'
    '  <CheatEntries>\n'
    '    <CheatEntry><ID>200</ID><Description>attach helper</Description>'
    '<VariableType>Auto Assembler Script</VariableType>'
    '<AssemblerScript>[ENABLE]\n{$lua}\nOpenProcess("Target.exe")\n{$asm}\n'
    '[DISABLE]\n</AssemblerScript></CheatEntry>\n'
    '    <CheatEntry><ID>201</ID><Description>pointer hook</Description>'
    '<VariableType>Auto Assembler Script</VariableType>'
    '<AssemblerScript>[ENABLE]\n'
    'aobscanmodule(synthPtr,Target.exe,54 46 57 48)\n'
    'registersymbol(synthPtr)\n'
    '[DISABLE]\n'
    'unregistersymbol(synthPtr)\n'
    '</AssemblerScript></CheatEntry>\n'
    '    <CheatEntry><ID>231</ID><Description>support link</Description>'
    '<VariableType>Auto Assembler Script</VariableType>'
    '<AssemblerScript>[ENABLE]\n{$lua}\nif syntaxcheck then return end\n'
    "ShellExecute('https://example.com/support')\n{$asm}\n[DISABLE]\n"
    '</AssemblerScript></CheatEntry>\n'
    '  </CheatEntries>\n'
    '</CheatTable>\n'
)


def table_with_script(version, script, entry_id=1):
    return (
        '<CheatTable CheatEngineTableVersion="%s"><CheatEntries>'
        '<CheatEntry><ID>%d</ID><Description>record %d</Description>'
        '<VariableType>Auto Assembler Script</VariableType>'
        '<AssemblerScript>%s</AssemblerScript></CheatEntry>'
        '</CheatEntries></CheatTable>'
        % (version, entry_id, entry_id, xml.sax.saxutils.escape(script))
    )


class Sc2TableWarningsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

    def compile_text(self, text):
        path = Path(self.directory.name) / "sample.CT"
        path.write_text(text, encoding="utf-8")
        return compile_table(path, "Target.exe")

    def test_sc2_shape_v46_table_carries_exactly_the_informational_warnings(self):
        plan = self.compile_text(SC2_SHAPE)
        self.assertEqual(plan["warnings"], [LUA_WARNING_NEW, SHELL_WARNING])
        self.assertEqual(plan["counts"]["blocked"], 0)
        self.assertEqual(plan["counts"]["total"], 3)

    def test_v46_table_no_longer_warns_about_the_newer_version(self):
        plan = self.compile_text(SC2_SHAPE)
        self.assertFalse(
            any("newer than the local CE reference" in warning
                for warning in plan["warnings"]),
            plan["warnings"])

    def test_v47_table_still_warns_against_reference_46(self):
        script = "[ENABLE]\nassert(Target.exe+10,00)\n[DISABLE]\nassert(Target.exe+10,01)\nTarget.exe+10:\ndb 00"
        plan = self.compile_text(table_with_script("47", script))
        self.assertIn(
            "Table version 47 is newer than the local CE reference (46); "
            "CE loading is unverified.",
            plan["warnings"])

    def test_lua_warning_is_informational_not_the_old_one(self):
        script = "[ENABLE]\n{$lua}\nlocal x = 1\n{$asm}\n[DISABLE]\n"
        plan = self.compile_text(table_with_script("45", script))
        self.assertIn(LUA_WARNING_NEW, plan["warnings"])
        self.assertNotIn(LUA_WARNING_OLD, plan["warnings"])

    def test_shell_execute_warning_states_the_safe_no_op(self):
        script = ("[ENABLE]\n{$lua}\nif syntaxcheck then return end\n"
                  "ShellExecute('https://example.com/support')\n{$asm}\n[DISABLE]\n")
        plan = self.compile_text(table_with_script("45", script))
        self.assertIn(SHELL_WARNING, plan["warnings"])
        self.assertNotIn(LEGACY_REVIEW_WARNING, plan["warnings"])

    def test_message_dialog_warning_names_the_missing_api(self):
        script = ("[ENABLE]\n{$lua}\nif syntaxcheck then return end\n"
                  "messageDialog('hi')\n{$asm}\n[DISABLE]\n")
        plan = self.compile_text(table_with_script("45", script))
        self.assertIn(MSGDLG_WARNING, plan["warnings"])
        self.assertNotIn(LEGACY_REVIEW_WARNING, plan["warnings"])

    def test_both_external_apis_yield_both_warnings(self):
        script = ("[ENABLE]\n{$lua}\nif syntaxcheck then return end\n"
                  "ShellExecute('https://example.com/support')\n"
                  "messageDialog('hi')\n{$asm}\n[DISABLE]\n")
        plan = self.compile_text(table_with_script("45", script))
        self.assertIn(SHELL_WARNING, plan["warnings"])
        self.assertIn(MSGDLG_WARNING, plan["warnings"])
        self.assertNotIn(LEGACY_REVIEW_WARNING, plan["warnings"])
