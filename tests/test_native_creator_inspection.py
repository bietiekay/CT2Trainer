"""WP-39: trainer-creator structured per-table inspection result.

Model-level coverage for the converter (trainer-creator) layer:

- ``table_inspection(plan)``: the structured per-table result
  ``{supported, blocked, top_reasons, warnings}`` derived from the compiled
  plan.  GUI-side derivation (no plan metadata), so the result is a pure
  deterministic function of the plan entries and warnings and is
  byte-verifiable against the plan; both plan validators stay untouched.
- Per-record blocked reasons surfaced verbatim and grouped deterministically;
  missing-Lua-API refusals (the existing runtime refusal taxonomy
  ``Unsupported CE Lua API: <name>`` from the declared read-only profile
  boundary) group by the named API, so the whole boundary reads as one
  decision.
- File-level diagnostics for the four hard failure classes (G4a-G4d):
  malformed/unreadable CT, bad target binding, unsupported plan schema,
  compile failure.
- Messagebox reservation: the four known classes classify to a named
  diagnostic (window rendering, no popup); every other failure stays
  unclassified and keeps the messagebox.

The synthetic fixtures mirror the pinned corpus ``case-19`` shapes
(duplicate-ID table with keep-first warnings, staged provider records) and
the fail-closed block shapes of the plan diagnostics.  A GUI smoke test is
intentionally out of scope (Windows-only).
"""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from ct2trainer.native.compiler import NativeCompileError, compile_table, validate_plan
from ct2trainer.native.converter import (InspectionError, file_diagnostic,
                                         missing_lua_api, table_inspection)
from ct2trainer.native.engine import validate_plan as engine_validate_plan
from ct2trainer.table import LEGACY_BINARY_CT_HEADER, TableError


PROCESS = "FixtureTarget.exe"

# ---------------------------------------------------------------------------
# Fixtures (synthetic CT bodies; shapes mirror the pinned corpus case-19)
# ---------------------------------------------------------------------------

SUPPORTED_CT = """<?xml version="1.0" encoding="utf-8"?>
<CheatTable CheatEngineTableVersion="45">
  <CheatEntries>
    <CheatEntry>
      <ID>0</ID>
      <Description>"health (supported value)"</Description>
      <Color>0075EA</Color>
      <VariableType>4 Bytes</VariableType>
      <Address>fixturetarget.exe+40</Address>
      <Value>0</Value>
    </CheatEntry>
    <CheatEntry>
      <ID>1</ID>
      <Description>"score (supported value)"</Description>
      <Color>0075EA</Color>
      <VariableType>2 Bytes</VariableType>
      <Address>fixturetarget.exe+44</Address>
      <Value>0</Value>
    </CheatEntry>
  </CheatEntries>
</CheatTable>
"""

WARNING_ONLY_CT = """<?xml version="1.0" encoding="utf-8"?>
<CheatTable CheatEngineTableVersion="45">
  <CheatEntries>
    <CheatEntry>
      <ID>0</ID>
      <Description>"hotkey value (supported)"</Description>
      <Color>0075EA</Color>
      <VariableType>4 Bytes</VariableType>
      <Address>fixturetarget.exe+50</Address>
      <Hotkeys>
        <Hotkey>12</Hotkey>
      </Hotkeys>
      <Value>0</Value>
    </CheatEntry>
  </CheatEntries>
  <LuaScript>local helper = 1</LuaScript>
  <Forms><Form Caption="settings"/></Forms>
</CheatTable>
"""

EXPECTED_WARNING_WARNINGS = [
    "Table Lua can run when Cheat Engine loads the table.",
    "Embedded CE forms are present; check UI conflicts.",
    "Table Lua is not executed on load. Read-only helpers replay in each Lua "
    "activation; top-level writes, callbacks and unsupported APIs block "
    "activation.",
    "Table-level sections not interpreted: Forms.",
    "Original CE record hotkeys are metadata only and are not registered.",
]

MIXED_CT = """<?xml version="1.0" encoding="utf-8"?>
<CheatTable CheatEngineTableVersion="45">
  <CheatEntries>
    <CheatEntry>
      <ID>0</ID>
      <Description>"value A (kept first occurrence of id 0)"</Description>
      <Color>0075EA</Color>
      <VariableType>4 Bytes</VariableType>
      <Address>fixturetarget.exe+40</Address>
      <Value>0</Value>
    </CheatEntry>
    <CheatEntry>
      <ID>0</ID>
      <Description>"duplicate group of id 0 (dropped: keep-first)"</Description>
      <Color>0075EA</Color>
      <GroupHeader>1</GroupHeader>
    </CheatEntry>
    <CheatEntry>
      <ID>5</ID>
      <Description>"base provider (kept first occurrence of id 5)"</Description>
      <Color>0075EA</Color>
      <VariableType>Auto Assembler Script</VariableType>
      <AssemblerScript>[ENABLE]
aobscanmodule(fixtureAnchor,fixturetarget.exe,48 8B 05 41 42 43 44 48 8B 0D 45 46 47 48)
alloc(fixtureCave,64,fixtureAnchor)
fixtureCave:
fixture_base:
registersymbol(fixture_base)
  dd 0
[DISABLE]
unregistersymbol(fixture_base)
dealloc(fixtureCave)</AssemblerScript>
      <CheatEntries>
      <CheatEntry>
        <ID>6</ID>
        <Description>"base (child of provider)"</Description>
        <Color>0075EA</Color>
        <VariableType>4 Bytes</VariableType>
        <Address>fixture_base</Address>
        <Value>0</Value>
      </CheatEntry>
      </CheatEntries>
    </CheatEntry>
    <CheatEntry>
      <ID>1</ID>
      <Description>"child of missing symbol A"</Description>
      <Color>0075EA</Color>
      <VariableType>4 Bytes</VariableType>
      <Address>MissingSymA+8</Address>
      <Value>0</Value>
    </CheatEntry>
    <CheatEntry>
      <ID>2</ID>
      <Description>"child of missing symbol A (same reason)"</Description>
      <Color>0075EA</Color>
      <VariableType>Float</VariableType>
      <Address>MissingSymA+16</Address>
      <Value>0</Value>
    </CheatEntry>
    <CheatEntry>
      <ID>3</ID>
      <Description>"child of missing symbol B"</Description>
      <Color>0075EA</Color>
      <VariableType>Byte</VariableType>
      <Address>MissingSymB</Address>
      <Value>0</Value>
    </CheatEntry>
  </CheatEntries>
</CheatTable>
"""

MISSING_API_CT = """<?xml version="1.0" encoding="utf-8"?>
<CheatTable CheatEngineTableVersion="45">
  <CheatEntries>
    <CheatEntry>
      <ID>0</ID>
      <Description>"kept base value (supported)"</Description>
      <Color>0075EA</Color>
      <VariableType>4 Bytes</VariableType>
      <Address>fixturetarget.exe+40</Address>
      <Value>0</Value>
    </CheatEntry>
    <CheatEntry>
      <ID>1</ID>
      <Description>"record blocked on the profile boundary (API 1)"</Description>
      <Color>0075EA</Color>
      <VariableType>4 Bytes</VariableType>
      <Address>MissingSymA+8</Address>
      <Value>0</Value>
    </CheatEntry>
    <CheatEntry>
      <ID>2</ID>
      <Description>"record blocked on the profile boundary (API 2)"</Description>
      <Color>0075EA</Color>
      <VariableType>4 Bytes</VariableType>
      <Address>MissingSymA+16</Address>
      <Value>0</Value>
    </CheatEntry>
    <CheatEntry>
      <ID>3</ID>
      <Description>"record blocked on the profile boundary (API 3)"</Description>
      <Color>0075EA</Color>
      <VariableType>Byte</VariableType>
      <Address>MissingSymB</Address>
      <Value>0</Value>
    </CheatEntry>
  </CheatEntries>
</CheatTable>
"""


def _write_ct(directory: Path, name: str, body: str) -> Path:
    path = directory / name
    path.write_text(body, encoding="utf-8")
    return path


def _compile(directory: Path, name: str, body: str) -> dict:
    return compile_table(_write_ct(directory, name, body), PROCESS)


class TableInspectionTests(unittest.TestCase):
    """Structured per-table result derived from the compiled plan."""

    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.directory = Path(self._temp.name)

    # (a) fully supported table -------------------------------------------

    def test_supported_table_yields_empty_reasons_and_warnings(self):
        plan = _compile(self.directory, "supported.ct", SUPPORTED_CT)
        result = table_inspection(plan)
        self.assertEqual(result, {
            "supported": 2,
            "blocked": 0,
            "top_reasons": [],
            "warnings": [],
        })
        self.assertEqual(plan["counts"]["supported"], 2)
        self.assertEqual(plan["counts"]["blocked"], 0)

    # (b) warning-only table -----------------------------------------------

    def test_warning_only_table_renders_warnings_without_blocking(self):
        plan = _compile(self.directory, "warnings.ct", WARNING_ONLY_CT)
        result = table_inspection(plan)
        self.assertEqual(result["supported"], 1)
        self.assertEqual(result["blocked"], 0)
        self.assertEqual(result["top_reasons"], [])
        # Warnings preserved verbatim, in plan order (table Lua, forms,
        # omitted sections, hotkeys).
        self.assertEqual(result["warnings"], EXPECTED_WARNING_WARNINGS)
        self.assertEqual(result["warnings"], plan["warnings"])
        # The result carries its own copy; plan mutations stay contained.
        result["warnings"].append("tampered")
        self.assertEqual(plan["warnings"], EXPECTED_WARNING_WARNINGS)

    # (c) mixed table -------------------------------------------------------

    def test_mixed_table_groups_top_reasons_deterministically(self):
        # case-19 shape: keep-first duplicate ID (warning only), a provider
        # script record with a staged relative-address child, plus three
        # blocked records in two distinct named reasons.
        plan = _compile(self.directory, "mixed.ct", MIXED_CT)
        result = table_inspection(plan)
        self.assertEqual(result["supported"], 3)
        self.assertEqual(result["blocked"], 3)
        self.assertEqual(result["top_reasons"], [
            {"key": "Required symbol has no unique supported provider: MissingSymA.",
             "reason": "Required symbol has no unique supported provider: MissingSymA.",
             "api": None,
             "count": 2,
             "records": [1, 2]},
            {"key": "Required symbol has no unique supported provider: MissingSymB.",
             "reason": "Required symbol has no unique supported provider: MissingSymB.",
             "api": None,
             "count": 1,
             "records": [3]},
        ])
        self.assertEqual(result["warnings"], [
            "Duplicate CheatEntry ID: 0 (kept first occurrence; "
            "dropped 1 duplicate record(s): duplicate group of id 0 "
            "(dropped: keep-first))"])

    def test_mixed_table_is_byte_verifiable_against_the_plan(self):
        plan = _compile(self.directory, "mixed.ct", MIXED_CT)
        result = table_inspection(plan)
        # Counts agree with the plan's own diagnostics.
        self.assertEqual(result["supported"], plan["counts"]["supported"])
        self.assertEqual(result["blocked"], plan["counts"]["blocked"])
        # Every blocked record carries its exact named reason; no reason is
        # lost or merged incorrectly.
        by_id = {entry["id"]: entry for entry in plan["entries"]}
        blocked_ids = {entry["id"] for entry in plan["entries"]
                       if not entry["supported"]}
        covered: set[int] = set()
        for group in result["top_reasons"]:
            covered.update(group["records"])
            self.assertEqual(group["count"], len(group["records"]))
            self.assertEqual(sorted(group["records"]), group["records"])
            for record_id in group["records"]:
                self.assertNotIn(record_id, covered - {record_id})
                self.assertEqual(by_id[record_id]["reason"], group["reason"])
        self.assertEqual(covered, blocked_ids)
        # The grouped (reason, count) pairs are exactly the plan's
        # blocked_reasons Counter, independently recomputed.
        self.assertEqual(
            {group["reason"]: group["count"] for group in result["top_reasons"]},
            plan["blocked_reasons"])
        # Deterministic: a second call on the same plan bytes is
        # byte-identical.
        self.assertEqual(
            json.dumps(result, sort_keys=True, separators=(",", ":")),
            json.dumps(table_inspection(copy.deepcopy(plan)),
                       sort_keys=True, separators=(",", ":")))

    # (d) missing-Lua-API block reasons grouped by the named API -----------

    def test_missing_lua_api_refusals_group_by_api(self):
        # The runtime host refuses CE Lua APIs outside the declared read-only
        # profile boundary with the exact taxonomy
        # 'Unsupported CE Lua API: <name>' (lua_host); a record whose
        # activation is blocked on that boundary carries that reason.  The
        # plan keeps it as plain reason text, so the plan stays valid with
        # the refusal rewritten onto the blocked records.
        plan = _compile(self.directory, "lua_api.ct", MISSING_API_CT)
        blocked = [entry for entry in plan["entries"] if not entry["supported"]]
        self.assertEqual([entry["id"] for entry in blocked], [1, 2, 3])
        refutations = {
            1: "Unsupported CE Lua API: createMemoryRecord",
            2: "Unsupported CE Lua API: createMemoryRecord",
            3: "Unsupported CE Lua API: addresslist.getMemoryRecordByID",
        }
        for entry in blocked:
            entry["reason"] = refutations[entry["id"]]
        from collections import Counter
        plan["blocked_reasons"] = dict(Counter(entry["reason"]
                                               for entry in plan["entries"]
                                               if not entry["supported"]))
        # Rewriting reasons changes no plan contract: BOTH validators still
        # accept the plan.
        validate_plan(plan)
        engine_validate_plan(plan)
        result = table_inspection(plan)
        self.assertEqual(result["supported"], 1)
        self.assertEqual(result["blocked"], 3)
        # Two distinct APIs, deterministic casefold order, records sorted.
        self.assertEqual(result["top_reasons"], [
            {"key": "addresslist.getMemoryRecordByID",
             "reason": "Unsupported CE Lua API: addresslist.getMemoryRecordByID",
             "api": "addresslist.getMemoryRecordByID",
             "count": 1,
             "records": [3]},
            {"key": "createMemoryRecord",
             "reason": "Unsupported CE Lua API: createMemoryRecord",
             "api": "createMemoryRecord",
             "count": 2,
             "records": [1, 2]},
        ])
        # The profile boundary reads as one decision: every group in this
        # result names the same existing refusal taxonomy.
        self.assertTrue(all(group["api"] is not None
                            for group in result["top_reasons"]))
        self.assertEqual(
            {group["reason"]: group["count"] for group in result["top_reasons"]},
            plan["blocked_reasons"])

    def test_missing_lua_api_helper_reuses_the_existing_taxonomy(self):
        self.assertEqual(missing_lua_api("Unsupported CE Lua API: createMemoryRecord"),
                         "createMemoryRecord")
        self.assertEqual(missing_lua_api("Unsupported CE Lua API: addresslist.getMemoryRecordByID"),
                         "addresslist.getMemoryRecordByID")
        # The prefix is the existing refusal string, not a new one.
        self.assertEqual(missing_lua_api("Unsupported CE Lua API:  "), None)
        self.assertIsNone(missing_lua_api(""))
        self.assertIsNone(missing_lua_api("Unsupported CE Lua API"))
        self.assertIsNone(missing_lua_api(
            "Required symbol has no unique supported provider: X."))
        self.assertIsNone(missing_lua_api(None))

    # ordering / edge cases on the pure function ----------------------------

    def test_top_reason_order_is_casefold_deterministic(self):
        plan = {
            "entries": [
                {"id": 5, "supported": False,
                 "reason": "Unsupported CE Lua API: ZetaAPI"},
                {"id": 1, "supported": False,
                 "reason": "Required symbol has no unique supported provider: alpha."},
                {"id": 3, "supported": False,
                 "reason": "Unsupported CE Lua API: BetaAPI"},
                {"id": 2, "supported": True, "reason": ""},
                {"id": 4, "supported": False,
                 "reason": "Unsupported CE Lua API: ZetaAPI"},
            ],
            "warnings": ["one"],
        }
        result = table_inspection(plan)
        self.assertEqual([group["key"] for group in result["top_reasons"]],
                         ["BetaAPI",
                          "Required symbol has no unique supported provider: alpha.",
                          "ZetaAPI"])
        zeta = result["top_reasons"][2]
        self.assertEqual(zeta, {"key": "ZetaAPI",
                                "reason": "Unsupported CE Lua API: ZetaAPI",
                                "api": "ZetaAPI", "count": 2, "records": [4, 5]})

    def test_inspection_refuses_malformed_shapes(self):
        with self.assertRaises(InspectionError) as ctx:
            table_inspection("not a plan")
        self.assertEqual(str(ctx.exception),
                         "Inspection input must be a plan dict.")
        with self.assertRaises(InspectionError):
            table_inspection({"entries": None, "warnings": []})
        with self.assertRaises(InspectionError):
            table_inspection({"entries": [], "warnings": []})
        with self.assertRaises(InspectionError):
            table_inspection({"entries": [42], "warnings": []})
        with self.assertRaises(InspectionError):
            table_inspection({"entries": [
                {"id": 1, "supported": True, "reason": ""},
                {"id": 1, "supported": True, "reason": ""},
            ], "warnings": []})
        with self.assertRaises(InspectionError):
            table_inspection({"entries": [
                {"id": 1, "supported": "yes", "reason": ""},
            ], "warnings": []})
        with self.assertRaises(InspectionError):
            table_inspection({"entries": [
                {"id": 1, "supported": True},
            ], "warnings": []})
        with self.assertRaises(InspectionError):
            table_inspection({"entries": [
                {"id": 1, "supported": True, "reason": ""},
            ], "warnings": ["ok", 42]})


class FileDiagnosticTests(unittest.TestCase):
    """File-level diagnostics for the four hard failure classes (G4a-G4d)."""

    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.directory = Path(self._temp.name)

    # the mapping itself -----------------------------------------------------

    def test_the_four_hard_classes_map_to_named_diagnostics(self):
        # G4a: malformed/unreadable CT (any TableError shape).
        self.assertEqual(file_diagnostic(TableError("Invalid CT XML: boom")),
                         "Malformed or unreadable CT table")
        self.assertEqual(
            file_diagnostic(TableError(
                "Legacy binary CT table (CHEATENGINE header): not supported — "
                "XML .CT expected.")),
            "Malformed or unreadable CT table")
        # G4b: bad target binding (the exact process-name refusal).
        self.assertEqual(
            file_diagnostic(NativeCompileError(
                "Process name must be an exact .exe basename without a path.")),
            "Bad target binding")
        # G4c: unsupported plan schema (the exact schema refusal).
        self.assertEqual(
            file_diagnostic(NativeCompileError(
                "Unsupported native plan schema or engine.")),
            "Unsupported plan schema")
        # G4d: compile failure (every other compile refusal).
        self.assertEqual(
            file_diagnostic(NativeCompileError(
                "Trainer title must be printable text up to 512 characters.")),
            "Compile failure")

    def test_unexpected_failures_stay_unclassified(self):
        self.assertIsNone(file_diagnostic(RuntimeError("boom")))
        self.assertIsNone(file_diagnostic(ValueError("unknown shape")))
        self.assertIsNone(file_diagnostic(OSError("drive gone")))

    # end-to-end through compile_table ---------------------------------------

    def test_malformed_ct_end_to_end_is_G4a(self):
        path = _write_ct(self.directory, "malformed.ct",
                         "<NotACheatTable><x/></NotACheatTable>")
        try:
            compile_table(path, PROCESS)
        except TableError as exc:
            self.assertEqual(file_diagnostic(exc),
                             "Malformed or unreadable CT table")
        else:
            self.fail("malformed CT did not refuse")

    def test_legacy_binary_ct_end_to_end_is_G4a(self):
        path = self.directory / "legacy.ct"
        path.write_bytes(LEGACY_BINARY_CT_HEADER + b"0\x00binary tail")
        try:
            compile_table(path, PROCESS)
        except TableError as exc:
            self.assertIn("Legacy binary CT table", str(exc))
            self.assertEqual(file_diagnostic(exc),
                             "Malformed or unreadable CT table")
        else:
            self.fail("legacy binary CT did not refuse")

    def test_missing_ct_file_end_to_end_is_G4a(self):
        path = self.directory / "absent.ct"
        try:
            compile_table(path, PROCESS)
        except TableError as exc:
            self.assertEqual(file_diagnostic(exc),
                             "Malformed or unreadable CT table")
        else:
            self.fail("missing CT did not refuse")

    def test_bad_target_binding_end_to_end_is_G4b(self):
        path = _write_ct(self.directory, "ok.ct", SUPPORTED_CT)
        for bad in ("game", "game.exe ", "C:\\games\\game.exe", ".exe", "game.exe.txt"):
            with self.subTest(bad=bad):
                try:
                    compile_table(path, bad)
                except NativeCompileError as exc:
                    self.assertEqual(str(exc),
                                     "Process name must be an exact .exe "
                                     "basename without a path.")
                    self.assertEqual(file_diagnostic(exc), "Bad target binding")
                else:
                    self.fail("bad target binding did not refuse")

    def test_compile_failure_end_to_end_is_G4d(self):
        path = _write_ct(self.directory, "ok.ct", SUPPORTED_CT)
        try:
            compile_table(path, PROCESS, title="x" * 513)
        except NativeCompileError as exc:
            self.assertEqual(str(exc),
                             "Trainer title must be printable text up to "
                             "512 characters.")
            self.assertEqual(file_diagnostic(exc), "Compile failure")
        else:
            self.fail("oversized title did not refuse")


class MessageboxReservationTests(unittest.TestCase):
    """The messagebox stays reserved for unexpected errors only.

    The GUI decision is exactly ``file_diagnostic(exc) is None``: a named
    diagnostic means the failure renders as a per-file diagnostic in the
    inspection window (no popup); None means the messagebox fires.
    """

    def test_known_failure_classes_never_raise_the_messagebox(self):
        known = (
            TableError("Invalid CT XML: boom"),
            TableError("Legacy binary CT table (CHEATENGINE header): "
                       "not supported — XML .CT expected."),
            NativeCompileError("Process name must be an exact .exe basename "
                               "without a path."),
            NativeCompileError("Unsupported native plan schema or engine."),
            NativeCompileError("Compile failure detail."),
        )
        for exc in known:
            with self.subTest(exc=exc):
                self.assertIsNotNone(file_diagnostic(exc),
                                     "known class must not use the messagebox")

    def test_unexpected_errors_keep_the_messagebox(self):
        for exc in (RuntimeError("nasm missing"), OSError("read failed"),
                    ValueError("unknown")):
            with self.subTest(exc=exc):
                self.assertIsNone(file_diagnostic(exc),
                                  "unknown class must keep the messagebox")


if __name__ == "__main__":
    unittest.main()
