"""WP-44: pre-[ENABLE] register declarations and inert-script demotion.

Pre-[ENABLE] ``registersymbol``/``registerlabel`` are accepted in both
dialects; the registered symbol enters ``provides`` and the register op
joins the ENABLE side only (release stays in the DISABLE phase).  A script
record whose source has no registered symbols and no guarded byte-patch in
either dialect is demoted to a supported, non-actionable inert heading:
no enable actions, no cascade promise, no async marker.  Genuinely refused
scripts stay blocked with their original reason.
"""
import tempfile
import unittest
import xml.sax.saxutils
from pathlib import Path

from ct2trainer.native import aa as aadata
from ct2trainer.native import aa_program as aa
from ct2trainer.native.aa import AAError
from ct2trainer.native.aa_program import ProgramError
from ct2trainer.native.compiler import NativeCompileError, compile_table, validate_plan
from ct2trainer.native.engine import validate_plan as validate_runtime_plan


def script_record(entry_id, script, label="Option", attributes=""):
    return (f'<CheatEntry><ID>{entry_id}</ID><Description>{label}</Description>'
            '<VariableType>Auto Assembler Script</VariableType>'
            f'<AssemblerScript {attributes}>{xml.sax.saxutils.escape(script)}</AssemblerScript></CheatEntry>')


INERT_SCRIPT = "[ENABLE]\n{ comment-only credits block }\n[DISABLE]\n"
REFUSED_SCRIPT = "[ENABLE]\ncreatethread(1)\n[DISABLE]\n"


class PreEnableRegisterDataDialectTests(unittest.TestCase):
    def _script(self, preamble_directive):
        return (preamble_directive + "\n"
                "[ENABLE]\nassert(address,90)\naddress:\ndb 90\n"
                "[DISABLE]\nassert(address,90)\naddress:\ndb 90\n"
                "unregistersymbol(address)\n")

    def test_registersymbol_before_enable_provides_and_enable_only(self):
        result = aadata.compile_script(self._script(
            "define(address,Target.exe+1000)\nregisterSymbol(address)"))
        self.assertEqual(result["provides"], ["address"])
        self.assertEqual([op for op in result["enable"] if op["op"] == "register"],
                         [{"op": "register", "symbol": "address"}])
        self.assertEqual([op for op in result["disable"] if op["op"] == "unregister"],
                         [{"op": "unregister", "symbol": "address"}])

    def test_registerlabel_before_enable_accepted(self):
        result = aadata.compile_script(self._script(
            "define(address,Target.exe+1000)\nregisterlabel(address)"))
        self.assertEqual(result["provides"], ["address"])
        self.assertEqual(len([op for op in result["enable"] if op["op"] == "register"]), 1)

    def test_unregistersymbol_before_enable_refused(self):
        with self.assertRaisesRegex(AAError,
                                    "Only define, label and register declarations are allowed before ENABLE."):
            aadata.compile_script(
                "unregistersymbol(foo)\n"
                "[ENABLE]\nassert(address,90)\naddress:\ndb 90\n"
                "[DISABLE]\nassert(address,90)\naddress:\ndb 90\n")

    def test_one_shot_gate_stays_strict(self):
        # A one-shot may never register: the unchanged one-shot refusal
        # fires when a register declaration sits inside the ENABLE section.
        with self.assertRaisesRegex(AAError, "One-shot scripts cannot register or unregister symbols"):
            aadata.compile_one_shot(
                "[ENABLE]\ndefine(alpha,Target.exe+10)\nregistersymbol(alpha)\n"
                "assert(alpha,90)\nalpha:\ndb 90")


class PreEnableRegisterNativeDialectTests(unittest.TestCase):
    def test_register_and_label_before_enable(self):
        source = ("define(address,0x1000)\nlabel(foo)\nregistersymbol(address)\n"
                  "[ENABLE]\nalloc(cave,100,address)\ncave:\nmov [rcx],0x11\n"
                  "0x1000:\njmp cave\n"
                  "[DISABLE]\n0x1000:\ndb B8 01 00 00 00\ndealloc(cave)\n")
        profile = aa.prepare_program(source, bitness=64)
        self.assertEqual(profile["provides"], ["address"])
        aa.validate_program(profile)

    def test_unregistersymbol_before_enable_refused(self):
        with self.assertRaisesRegex(ProgramError,
                                    "Only define, label and register are permitted before ENABLE."):
            aa.prepare_program(
                "unregistersymbol(x)\n[ENABLE]\n0x1000:\ndb 01\n[DISABLE]\n",
                bitness=64)


class InertScriptDemotionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.table_path = Path(self.directory.name) / "inert.CT"

    def compile(self, body, selected_ids=None):
        self.table_path.write_text(
            '<CheatTable CheatEngineTableVersion="52"><CheatEntries>' + body
            + '</CheatEntries></CheatTable>', encoding="utf-8")
        return compile_table(self.table_path, "Target.exe", selected_ids=selected_ids)

    def entry(self, plan, entry_id=0):
        return next(entry for entry in plan["entries"] if entry["id"] == entry_id)

    def test_no_action_script_demoted_to_supported_inert_heading(self):
        plan = self.compile(script_record(7, INERT_SCRIPT, label="Author"))
        entry = self.entry(plan, 7)
        self.assertTrue(entry["supported"])
        self.assertEqual(entry["kind"], "heading")
        self.assertEqual(entry["reason"],
                         "Inert script: no registered symbols and no guarded byte-patch "
                         "action; activation is a verified no-op.")
        for key in ("enable", "disable", "program", "lua_program", "global_program"):
            self.assertNotIn(key, entry)
        self.assertEqual(entry["requires"], [])
        self.assertEqual(entry["provides"], [])
        self.assertEqual(plan["counts"],
                         {"total": 1, "supported": 1, "actionable": 0,
                          "blocked": 0, "headings": 1})
        validate_plan(plan)
        validate_runtime_plan(plan)

    def test_genuinely_refused_script_stays_blocked(self):
        plan = self.compile(script_record(1, REFUSED_SCRIPT))
        entry = self.entry(plan, 1)
        self.assertFalse(entry["supported"])
        self.assertEqual(entry["kind"], "blocked")
        self.assertIn("createthread", entry["reason"])
        self.assertNotIn("enable", entry)
        self.assertNotIn("disable", entry)

    def test_inert_script_never_carries_async_marker(self):
        plan = self.compile(script_record(7, INERT_SCRIPT, label="Author",
                                          attributes='Async="1"'))
        entry = self.entry(plan, 7)
        self.assertTrue(entry["supported"])
        self.assertNotIn("async", entry)
        validate_plan(plan)

    def test_inert_child_is_excluded_from_parent_cascade(self):
        parent = ('<CheatEntry><ID>0</ID><Description>Group</Description>'
                  '<GroupHeader>1</GroupHeader>'
                  '<Options moActivateChildrenAsWell="1"/><CheatEntries>')
        child = script_record(8, INERT_SCRIPT, label="Author")
        plan = self.compile(parent + child + '</CheatEntries></CheatEntry>')
        self.assertNotIn("parent_relations", plan)
        self.assertNotIn("parent_activation", plan["entries"][0])
        self.assertEqual(plan["entries"][0]["reason"],
                         "Navigation heading; CE group activation is not executed.")
        validate_plan(plan)

    def test_forged_inert_entry_refused(self):
        plan = self.compile(script_record(7, INERT_SCRIPT, label="Author"))
        plan["entries"][0]["provides"] = ["Forged"]
        with self.assertRaises(NativeCompileError):
            validate_plan(plan)


if __name__ == "__main__":
    unittest.main()
