"""0.42 (B)/(C): CE 7.5 cleanup parity + API-export registry extension.

(B) A disable-phase cleanup name that NO program owns is a silent CE 7.5
no-op (autoassembler.pas L2492-2525 unregistersymbol / L2625-2669 dealloc,
read-only reference): the name is dropped from the node and recorded in
the program's ``unowned_cleanup_dropped`` field instead of refusing the
program.  A name owned by another supported record keeps the WP-37 named
handover refusal: the owning record releases it exactly once on its own
deactivation, so a second release is a real cross-record hazard, not a
CE no-op.  The plan-level re-check re-blocks a first-pass-supported
record when one of its dropped names is live-registered by a supported
record (WP-37 handover context or another record's entry-level
provides); a name nobody supports keeps the no-op and the record stays
supported - the corpus cascade the 0.41 cleanup-ownership refusal
blocked (re2 12997 shape, HFW/DS2 cleanup roots).

(C) The bounded Windows API export registry gains the two corpus shapes:
``call Sleep`` (kernel32.dll) and ``call ShowWindow`` (user32.dll)
resolve with the exact ``api_exports`` plan marker, the same contract as
the RT-4.2 user32 entries; a bare API name in a value address
expression keeps the classic unsupported-provider refusal (the marker
is a script-record feature).

Self-contained synthetic fixtures (no TableReferences, no CE inputs).
"""
import tempfile
import unittest
from pathlib import Path

from ct2trainer.native.aa_program import ProgramError, prepare_program
from ct2trainer.native.compiler import compile_table, validate_plan
from test_native_compiler import script_record, value_record

PROCESS = "ct2parity.exe"


def write_table(directory: Path, body: str, name: str = "parity.ct") -> Path:
    path = Path(directory) / name
    path.write_text('<CheatTable CheatEngineTableVersion="52"><CheatEntries>'
                    + body + '</CheatEntries></CheatTable>',
                    encoding="utf-8")
    return path


class ProgramCleanupNoOpTests(unittest.TestCase):
    """Program level: the unowned cleanup no-op + the owned refusal."""

    def test_unowned_unregistersymbol_is_dropped(self):
        # The re2 trigger shape: the cleanup list mixes the program's own
        # registered symbol with a name nobody registers (label-only in
        # the corpus).  The owned name stays, the unowned name is dropped
        # and recorded.
        program = prepare_program(
            "[ENABLE]\nalloc(cave,0x100)\nrootsym:\ndb 01\n"
            "registersymbol(rootsym)\n"
            "[DISABLE]\nrootsym:\ndb 00\n"
            "unregistersymbol(rootsym,ghost)\ndealloc(cave)", "Target.exe")
        node = next(n for n in program["disable"] if n["op"] == "unregister")
        self.assertEqual(node["symbols"], ["rootsym"])
        self.assertEqual(program["unowned_cleanup_dropped"], ["ghost"])
        self.assertNotIn("ghost", program["requires"])
        self.assertNotIn("ghost", program["provides"])

    def test_unowned_dealloc_name_is_dropped(self):
        # CE 7.5 dealloc() searches only this program's own allocation
        # set: an unknown allocation name is silently ignored.
        program = prepare_program(
            "[ENABLE]\nalloc(memory,0x100)\n[DISABLE]\ndealloc(memory,zz)",
            "Target.exe")
        node = next(n for n in program["disable"] if n["op"] == "dealloc")
        self.assertEqual(node, {"op": "dealloc", "symbols": ["memory"]})
        self.assertEqual(program["unowned_cleanup_dropped"], ["zz"])

    def test_dropped_names_are_sorted_and_deduped(self):
        program = prepare_program(
            "[ENABLE]\nalloc(cave,0x100)\n[DISABLE]\n"
            "dealloc(cave,Zeta, alpha)\ndealloc(Zeta)", "Target.exe")
        nodes = [n for n in program["disable"] if n["op"] == "dealloc"]
        self.assertEqual(nodes[0]["symbols"], ["cave"])
        self.assertEqual(nodes[1]["symbols"], [])
        self.assertEqual(program["unowned_cleanup_dropped"], ["alpha", "Zeta"])

    def test_external_owned_name_keeps_the_named_refusal(self):
        # The WP-37 handover boundary is unchanged: a name owned by
        # another record (external context) is still refused, now with
        # the owning record named.
        with self.assertRaisesRegex(
                ProgramError,
                "externally owned symbol zz \\(owned by record 7\\)."):
            prepare_program("[ENABLE]\nalloc(memory,0x100)\n[DISABLE]\ndealloc(memory,zz)",
                            "Target.exe",
                            external_owned=frozenset({"zz"}),
                            external_owners={"zz": 7})

    def test_wildcard_cleanup_ignores_external_names(self):
        # The wildcard expands only to this program's own names; external
        # owned names are never touched and nothing is dropped.
        program = prepare_program(
            "[ENABLE]\nalloc(cave,0x100)\nsym:\ndb 01\nregistersymbol(sym)\n"
            "[DISABLE]\nsym:\ndb 00\nunregistersymbol(*)\ndealloc(*)",
            "Target.exe",
            external_owned=frozenset({"other"}),
            external_owners={"other": 3})
        unregister = next(n for n in program["disable"] if n["op"] == "unregister")
        dealloc = next(n for n in program["disable"] if n["op"] == "dealloc")
        self.assertEqual(unregister["symbols"], ["sym"])
        self.assertEqual(dealloc["symbols"], ["cave"])
        self.assertEqual(program["unowned_cleanup_dropped"], [])


class PlanCleanupRecheckTests(unittest.TestCase):
    """Plan level: the table-wide ownership re-check after the first pass."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def _plan(self, body: str) -> dict:
        return compile_table(write_table(self.root, body), PROCESS)

    def test_handover_cleanup_recheck_blocks_the_consumer(self):
        # Record 1 owns 'hand' through its allocation-only program
        # (WP-37 handover); record 2's static cleanup releases the same
        # name.  The first pass drops the name (no table context), the
        # re-check re-blocks record 2 with the named handover reason -
        # record 1 releases the symbol exactly once on its own
        # deactivation.
        provider = (
            "[ENABLE]\n"
            "alloc(hand, 0x100)\n"
            "registersymbol(hand)\n"
            "[DISABLE]\n"
            "unregistersymbol(hand)\n"
            "dealloc(hand)\n"
        )
        consumer = (
            "[ENABLE]\n"
            "hand+4:\n"
            "  db 01\n"
            "[DISABLE]\n"
            "hand+4:\n"
            "  db 00\n"
            "  unregistersymbol(hand)\n"
        )
        e = {entry["id"]: entry
             for entry in self._plan(script_record(1, provider, "provider")
                                     + script_record(2, consumer, "consumer"))
             ["entries"]}
        self.assertTrue(e[1]["supported"], e[1].get("reason"))
        self.assertFalse(e[2]["supported"])
        self.assertEqual(e[2]["reason"],
                         "Program may not unregister or deallocate the "
                         "externally owned symbol hand (owned by record 1).")
        validate_plan(self._plan(script_record(1, provider, "provider")
                                 + script_record(2, consumer, "consumer")))

    def test_unowned_cleanup_cascade_unblocks_the_dependent(self):
        # The corpus root shape (re2 12997): the provider's cleanup
        # releases a name nobody registers, so the provider stays
        # supported and the dependent resolves its symbol - before 0.42
        # the generic cleanup refusal blocked the provider and its
        # dependents with the no-unique-provider cascade.
        provider = (
            "[ENABLE]\n"
            "alloc(cave, 0x100)\n"
            "rootsym:\n"
            "  db 01\n"
            "registersymbol(rootsym)\n"
            "[DISABLE]\n"
            "rootsym:\n"
            "  db 00\n"
            "  unregistersymbol(rootsym, ghostzz)\n"
            "  dealloc(cave)\n"
        )
        plan = self._plan(script_record(1, provider, "provider")
                          + value_record(2, "rootsym+8"))
        e = {entry["id"]: entry for entry in plan["entries"]}
        self.assertTrue(e[1]["supported"], e[1].get("reason"))
        self.assertEqual(e[1]["program"]["unowned_cleanup_dropped"],
                         ["ghostzz"])
        unregister = next(n for n in e[1]["program"]["disable"]
                          if n["op"] == "unregister")
        self.assertEqual(unregister["symbols"], ["rootsym"])
        self.assertTrue(e[2]["supported"], e[2].get("reason"))
        self.assertEqual(e[2]["dependency_ids"], [1])
        validate_plan(plan)


class ApiExportRegistryTests(unittest.TestCase):
    """(C): the two corpus API shapes resolve with the plan marker."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def test_sleep_and_showwindow_calls_get_the_markers(self):
        sleep_record = (
            "[ENABLE]\n"
            "alloc(thread, 0x1000)\n"
            "registersymbol(thread)\n"
            "thread:\n"
            "  mov rcx, 10\n"
            "  call Sleep\n"
            "  ret\n"
            "[DISABLE]\n"
            "unregistersymbol(thread)\n"
            "dealloc(thread)\n"
        )
        window_record = (
            "[ENABLE]\n"
            "alloc(thread, 0x1000)\n"
            "registersymbol(thread)\n"
            "thread:\n"
            "  mov rcx, 0\n"
            "  mov rdx, 0\n"
            "  call ShowWindow\n"
            "  ret\n"
            "[DISABLE]\n"
            "unregistersymbol(thread)\n"
            "dealloc(thread)\n"
        )
        plan = compile_table(write_table(
            self.root, script_record(1, sleep_record, "sleep thread")
            + script_record(2, window_record, "window thread")), PROCESS)
        e = {entry["id"]: entry for entry in plan["entries"]}
        for entry_id, export, module in ((1, "Sleep", "kernel32.dll"),
                                         (2, "ShowWindow", "user32.dll")):
            with self.subTest(entry_id=entry_id):
                self.assertTrue(e[entry_id]["supported"],
                                e[entry_id].get("reason"))
                self.assertEqual(e[entry_id]["api_exports"],
                                 {export: module})
                self.assertEqual(e[entry_id]["requires"], [export])
                self.assertEqual(e[entry_id]["dependency_ids"], [])
                self.assertNotIn("staged", e[entry_id])
        validate_plan(plan)

    def test_value_expression_with_bare_api_name_stays_blocked(self):
        # The marker is a script-record feature: a value record whose
        # address expression names the bare API export keeps the classic
        # generic refusal and never gains a marker.
        plan = compile_table(write_table(
            self.root, script_record(1,
                                     "[ENABLE]\n"
                                     "alloc(thread, 0x1000)\n"
                                     "registersymbol(thread)\n"
                                     "thread:\n"
                                     "  mov rcx, 10\n"
                                     "  call Sleep\n"
                                     "  ret\n"
                                     "[DISABLE]\n"
                                     "unregistersymbol(thread)\n"
                                     "dealloc(thread)\n",
                                     "sleep thread")
            + value_record(2, "Sleep+4")), PROCESS)
        e = {entry["id"]: entry for entry in plan["entries"]}
        self.assertTrue(e[1]["supported"], e[1].get("reason"))
        self.assertFalse(e[2]["supported"])
        self.assertEqual(e[2]["reason"],
                         "Required symbol has no unique supported provider: "
                         "Sleep.")
        self.assertNotIn("api_exports", e[2])


if __name__ == "__main__":
    unittest.main()
