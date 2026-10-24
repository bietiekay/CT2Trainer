"""RT-4.6: actionable per-symbol report for never-registered requirements.

When a requirement has no supported provider and no table-level fallback
(UDS / table Lua / user-symbol import), the raw-source registration survey
splits the report: a symbol registered somewhere in the table source
(provider record exists but is blocked for another reason) or a bare
``call`` target (Windows API export territory) keeps the classic generic
reason, while a name registered nowhere gets the actionable per-symbol
report that names the referring record and both remediations.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import xml.sax.saxutils

from ct2trainer.native.compiler import (NativeCompileError, _symbol_source_survey,
                                        compile_table)

PROCESS = "FixtureTarget.exe"


def table_xml(body: str) -> str:
    return (
        '<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
        + body
        + "</CheatEntries></CheatTable>"
    )


def value_entry(entry_id: int, description: str, address: str) -> str:
    return (
        f'<CheatEntry><ID>{entry_id}</ID>'
        f'<Description>{description}</Description>'
        f"<VariableType>4 Bytes</VariableType>"
        f"<Address>{xml.sax.saxutils.escape(address)}</Address></CheatEntry>"
    )


def script_entry(entry_id: int, description: str, script: str) -> str:
    return (
        f'<CheatEntry><ID>{entry_id}</ID>'
        f'<Description>{description}</Description>'
        f"<VariableType>Auto Assembler Script</VariableType>"
        f"<AssemblerScript>{xml.sax.saxutils.escape(script)}</AssemblerScript>"
        f"</CheatEntry>"
    )


def plan_for(body: str) -> dict:
    with tempfile.TemporaryDirectory(prefix="ct2-rt46-report-") as directory:
        path = Path(directory) / "probe.ct"
        path.write_text(table_xml(body), encoding="utf-8")
        return compile_table(str(path), PROCESS)


GENERIC = "Required symbol has no unique supported provider: {sym}."
NEW = ("Required symbol '{sym}' is not registered anywhere in this table "
       "(referenced by '{path}'): no record defines it and it is not a "
       "user-defined symbol. Import it as a user symbol with its target "
       "address, or add a record that registers it "
       "(registersymbol/registerSymbol/label/aobscan).")


class SurveyMarkerTests(unittest.TestCase):
    """Registration-evidence markers recognized by the raw-source survey."""

    def _survey(self, *scripts: str):
        return _symbol_source_survey({i + 1: s for i, s in enumerate(scripts)})

    def test_registration_call_markers(self):
        registered, _ = self._survey(
            "registersymbol(A, B)",
            "registerlabel(C, D)")
        self.assertEqual({"a", "b", "c", "d"}, registered)

    def test_lua_register_symbol_quoted_name_is_recognized(self):
        # The Lua registerSymbol(name, address, create?) form carries extra
        # arguments; the pure-text survey is fail-safe (it may only add
        # evidence), so the quoted symbol name must be recognized and the
        # extra arguments stay harmless evidence.
        registered, _ = self._survey('registerSymbol("Quoted", 0, true)')
        self.assertIn("quoted", registered)

    def test_label_directive_and_define_markers(self):
        registered, _ = self._survey(
            "label(C, D)",
            "define(E, 1234)",
            "{$define F 7}")
        self.assertEqual({"c", "d", "e", "f"}, registered)

    def test_aobscan_first_argument_markers(self):
        registered, _ = self._survey(
            'aobscan(G, "00 11 22")',
            "aobscanmodule(H, 'M', '00 11 22')")
        self.assertEqual({"g", "h"}, registered)

    def test_positional_label_marker(self):
        registered, _ = self._survey("SomeLabel:\ndb 90")
        self.assertIn("somelabel", registered)

    def test_bare_call_target(self):
        registered, targets = self._survey(
            "FixtureTarget.exe+40:\ncall GetAsyncKeyState")
        self.assertEqual(set(), registered)
        self.assertEqual({"getasynckeystate"}, targets)

    def test_call_targets_with_dot_or_hyphen_continuations_do_not_register(self):
        # `call user32.X` is module-qualified export territory and
        # `call ctts-...` continues past the first token: neither may
        # contribute a bare-target entry.
        _, targets = self._survey(
            "call user32.GetAsyncKeyState",
            "call ctts-something")
        self.assertEqual(set(), targets)


class ClassificationTests(unittest.TestCase):
    """Zero-candidate branch: the survey decides the report wording."""

    def test_unregistered_symbol_gets_the_actionable_report(self):
        plan = plan_for(value_entry(1, "Missing ref", "MissingA+4"))
        entry = plan["entries"][0]
        self.assertFalse(entry["supported"])
        self.assertEqual(
            entry["reason"], NEW.format(sym="MissingA", path="Missing ref"))
        self.assertEqual(entry["requires"], ["MissingA"])

    def test_each_referring_record_names_its_own_path(self):
        plan = plan_for(value_entry(1, "Ref one", "MissingA")
                        + value_entry(2, "Ref two", "MissingA+8"))
        by_id = {entry["id"]: entry for entry in plan["entries"]}
        self.assertEqual(by_id[1]["reason"],
                         NEW.format(sym="MissingA", path="Ref one"))
        self.assertEqual(by_id[2]["reason"],
                         NEW.format(sym="MissingA", path="Ref two"))

    def test_symbol_registered_in_a_blocked_provider_keeps_the_generic_reason(self):
        # The provider record registers MissingA in its raw source but is
        # blocked itself (registering a symbol it does not own), so the
        # survey sees the registration and the consumer keeps the classic
        # generic report.
        plan = plan_for(
            script_entry(1, "Provider",
                         "[ENABLE]\nregistersymbol(MissingA)\n[DISABLE]\n")
            + value_entry(2, "Consumer", "MissingA"))
        by_id = {entry["id"]: entry for entry in plan["entries"]}
        self.assertFalse(by_id[1]["supported"])
        self.assertEqual(by_id[2]["reason"], GENERIC.format(sym="MissingA"))

    def test_bare_call_target_keeps_the_generic_reason(self):
        plan = plan_for(script_entry(
            1, "Caller",
            "[ENABLE]\nFixtureTarget.exe+40:\ncall GetAsyncKeyState\n"
            "[DISABLE]\nFixtureTarget.exe+40:\ndb 00 00 00 00 00"))
        entry = plan["entries"][0]
        self.assertFalse(entry["supported"])
        self.assertEqual(entry["reason"],
                         GENERIC.format(sym="GetAsyncKeyState"))

    def test_module_qualified_call_never_registers_a_bare_target(self):
        # `call user32.X` tokens are module-qualified (a dot continuation),
        # so no bare target enters the survey; the record stays supported
        # at compile time (module exports resolve at link time).
        plan = plan_for(script_entry(
            1, "Caller",
            "[ENABLE]\nFixtureTarget.exe+40:\ncall user32.GetAsyncKeyState\n"
            "[DISABLE]\nFixtureTarget.exe+40:\ndb 00 00 00 00 00"))
        entry = plan["entries"][0]
        self.assertTrue(entry["supported"], entry["reason"])
        self.assertNotIn(
            "Required symbol", entry.get("reason") or "")


if __name__ == "__main__":
    unittest.main()
