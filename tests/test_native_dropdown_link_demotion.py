"""Dangling dropdown link demotion (WP-45, GC-E9).

CE keeps a record whose ``DropDownListLink`` no longer matches any record
label writable: the dropdown simply shows an empty list.  The native
compiler now mirrors that fail-open behavior for the missing-target case
only: the record stays supported, the linked dropdown is demoted to an
empty plain list (no ``link_target_id``), and a named plan warning carries
the exact missing-target refusal text.  Ambiguous targets (two or more
labels case-folding to the same name) and chained links keep their hard
refusals byte-for-byte, linked String dropdowns keep their separate
literal-profile refusal, and the dynamic-address-provider adoption path
applies the same demotion to adopted relative values.
"""
from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path

from test_native_engine_code import Coordinator
from test_native_lua_activation import Memory

from ct2trainer.native.compiler import (compile_table, validate_plan)
from ct2trainer.native.engine import (TrainerEngine,
                                      validate_plan as validate_engine_plan)

PROCESS = "FixtureTarget.exe"
DEMOTE_SUFFIX = "The linked dropdown is demoted to an empty list."


def demotion_warnings(plan):
    """Only the named demotion warnings (the fixture also emits the
    {$lua} provenance warning for its provider script)."""
    return [warning for warning in plan["warnings"]
            if warning.endswith(DEMOTE_SUFFIX)]


def write_table(root: Path, body: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    table = root / "dropdown.ct"
    table.write_text(
        '<CheatTable CheatEngineTableVersion="45"><CheatEntries>' + body
        + '</CheatEntries></CheatTable>',
        encoding="utf-8")
    return table


def value_record(record_id, address, extra=""):
    return (f'<CheatEntry><ID>{record_id}</ID>'
            f'<Description>"Value {record_id}"</Description>'
            f'<VariableType>4 Bytes</VariableType><Address>{address}</Address>'
            f'{extra}<Value>0</Value></CheatEntry>')


class DropdownLinkDemotionPlanTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def compile(self, body):
        return compile_table(write_table(self.root, body), PROCESS)

    def demotion_warnings(self, plan):
        return demotion_warnings(plan)

    def test_missing_target_demotes_the_record_with_a_named_warning(self):
        plan = self.compile(
            value_record(0, "1000")
            + value_record(1, "1040",
                           extra='<DropDownListLink>Ghost List</DropDownListLink>'))
        entry = plan["entries"][1]
        self.assertTrue(entry["supported"], entry["reason"])
        self.assertEqual(entry["reason"], "")
        self.assertEqual(entry["dropdown"], {"choices": [], "read_only": False})
        self.assertNotIn("link_target_id", entry["dropdown"])
        self.assertEqual(self.demotion_warnings(plan), [
            "Record 1 ('Value 1'): Dropdown link target is missing: 'Ghost List' "
            "matches no record label. " + DEMOTE_SUFFIX])
        validate_plan(plan)
        validate_engine_plan(plan)

    def test_ambiguous_target_keeps_the_exact_hard_refusal(self):
        plan = self.compile(
            '<CheatEntry><ID>0</ID><Description>Twin</Description>'
            '<VariableType>4 Bytes</VariableType><Address>1000</Address>'
            '<DropDownList>1:One</DropDownList></CheatEntry>'
            '<CheatEntry><ID>1</ID><Description>twin</Description>'
            '<VariableType>4 Bytes</VariableType><Address>1001</Address>'
            '<DropDownList>2:Two</DropDownList></CheatEntry>'
            + value_record(2, "1002",
                           extra='<DropDownListLink>TWIN</DropDownListLink>'))
        entry = plan["entries"][2]
        self.assertFalse(entry["supported"])
        self.assertEqual(entry["reason"],
                         "Dropdown link target is ambiguous: 'TWIN' matches 2 record labels.")
        self.assertEqual(self.demotion_warnings(plan), [])
        validate_plan(plan)
        validate_engine_plan(plan)

    def test_chained_target_keeps_the_exact_hard_refusal(self):
        plan = self.compile(
            value_record(0, "2000",
                         extra='<DropDownList>1:One</DropDownList>')
            + value_record(1, "2001",
                           extra='<DropDownListLink>Value 0</DropDownListLink>')
            + value_record(2, "2002",
                           extra='<DropDownListLink>Value 1</DropDownListLink>'))
        self.assertTrue(plan["entries"][1]["supported"])
        self.assertFalse(plan["entries"][2]["supported"])
        self.assertEqual(plan["entries"][2]["reason"],
                         "Chained dropdown links are unsupported.")
        self.assertEqual(self.demotion_warnings(plan), [])
        validate_plan(plan)
        validate_engine_plan(plan)

    def test_resolved_link_stays_unchanged_without_warnings(self):
        plan = self.compile(
            value_record(0, "3000",
                         extra='<DropDownList>0:Off\n1:On</DropDownList>')
            + value_record(1, "3001",
                           extra='<DropDownListLink>Value 0</DropDownListLink>'))
        entry = plan["entries"][1]
        self.assertTrue(entry["supported"], entry["reason"])
        self.assertEqual(entry["dropdown"],
                         {"choices": [{"value": "0", "description": "Off"},
                                      {"value": "1", "description": "On"}],
                          "read_only": False, "link_target_id": 0})
        self.assertEqual(plan["warnings"], [])
        validate_plan(plan)
        validate_engine_plan(plan)

    def test_multiple_missing_targets_warn_in_document_order(self):
        plan = self.compile(
            value_record(0, "4000")
            + value_record(1, "4001",
                           extra='<DropDownListLink>Ghost One</DropDownListLink>')
            + value_record(2, "4002",
                           extra='<DropDownListLink>Ghost Two</DropDownListLink>'))
        for record in (1, 2):
            self.assertTrue(plan["entries"][record]["supported"])
            self.assertEqual(plan["entries"][record]["dropdown"],
                             {"choices": [], "read_only": False})
        self.assertEqual(self.demotion_warnings(plan), [
            "Record 1 ('Value 1'): Dropdown link target is missing: 'Ghost One' "
            "matches no record label. " + DEMOTE_SUFFIX,
            "Record 2 ('Value 2'): Dropdown link target is missing: 'Ghost Two' "
            "matches no record label. " + DEMOTE_SUFFIX])
        validate_plan(plan)
        validate_engine_plan(plan)

    def test_string_dropdown_link_keeps_its_separate_hard_refusal(self):
        plan = self.compile(
            value_record(0, "5000")
            + '<CheatEntry><ID>1</ID><Description>"linked string"</Description>'
              '<VariableType>String</VariableType><Address>5040</Address>'
              '<Length>32</Length>'
              '<DropDownListLink>Ghost List</DropDownListLink></CheatEntry>')
        entry = plan["entries"][1]
        self.assertFalse(entry["supported"])
        self.assertEqual(entry["reason"],
                         "Linked String dropdowns require a separate literal profile.")
        self.assertEqual(self.demotion_warnings(plan), [])
        validate_plan(plan)
        validate_engine_plan(plan)


PROVIDER_SOURCE = (
    "[ENABLE]\n{$lua}\nif not syntaxcheck then\n"
    "registerSymbol('BaseAddr', readQword('0x1008'))\nend\n{$asm}\n"
    "[DISABLE]\n{$lua}\nunregisterSymbol('BaseAddr')\n{$asm}")


def write_provider_table(root: Path, child_link: str = "") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    table = root / "provider.ct"
    table.write_text(
        '<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
        '<CheatEntry><ID>3000</ID><Description>"Dynamic base"'
        '</Description><VariableType>Auto Assembler Script</VariableType>'
        f'<AssemblerScript>{PROVIDER_SOURCE}</AssemblerScript>'
        '<CheatEntries>'
        '<CheatEntry><ID>3001</ID><Description>"Provider group"'
        '</Description><GroupHeader>1</GroupHeader>'
        '<CheatEntries>'
        f'<CheatEntry><ID>3002</ID><Description>"First"'
        '</Description><VariableType>4 Bytes</VariableType><Address>+10</Address>'
        f'<DropDownListLink>{child_link}</DropDownListLink></CheatEntry>'
        '<CheatEntry><ID>3003</ID><Description>"Second"</Description>'
        '<VariableType>4 Bytes</VariableType><Address>+14</Address></CheatEntry>'
        '</CheatEntries>'
        '</CheatEntry>'
        '</CheatEntries>'
        '</CheatEntry>'
        '<CheatEntry><ID>3010</ID><Description>"Sibling"</Description>'
        '<VariableType>4 Bytes</VariableType><Address>1060</Address></CheatEntry>'
        '</CheatEntries></CheatTable>',
        encoding="utf-8")
    return table


ADOPTED_REASON = ("Native relative value; the inherited base is resolved "
                  "at runtime from the dynamic address provider.")


class DropdownLinkDemotionAdoptionTests(unittest.TestCase):
    """WP-38 adoption path: the same demotion applies to adopted values."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_adopted_relative_value_demotes_its_dangling_link(self):
        table = write_provider_table(self.root, child_link="Ghost List")
        plan = compile_table(table, PROCESS)
        by_id = {entry["id"]: entry for entry in plan["entries"]}
        child = by_id[3002]
        self.assertEqual(child["kind"], "value", child["reason"])
        self.assertTrue(child["supported"], child["reason"])
        self.assertEqual(child["address"], "+10")
        self.assertEqual(child["address_profile"], "expression/v1")
        self.assertEqual(child["reason"], ADOPTED_REASON)
        self.assertEqual(child["dropdown"], {"choices": [], "read_only": False})
        self.assertNotIn("link_target_id", child["dropdown"])
        self.assertEqual(by_id[3001]["address_provider"],
                         {"provider_id": 3000, "symbol": "BaseAddr"})
        self.assertEqual(demotion_warnings(plan), [
            "Record 3002 ('First'): Dropdown link target is missing: 'Ghost List' "
            "matches no record label. " + DEMOTE_SUFFIX])
        # The sibling relative child without a link adopts normally.
        self.assertTrue(by_id[3003]["supported"], by_id[3003]["reason"])
        validate_plan(plan)
        validate_engine_plan(plan)

    def test_adopted_relative_value_without_link_keeps_no_warning(self):
        table = write_provider_table(self.root)
        plan = compile_table(table, PROCESS)
        by_id = {entry["id"]: entry for entry in plan["entries"]}
        self.assertTrue(by_id[3002]["supported"], by_id[3002]["reason"])
        # Adopted profile values always carry the plain dropdown shape;
        # without a link target it stays an empty plain list, no warning.
        self.assertEqual(by_id[3002]["dropdown"],
                         {"choices": [], "read_only": False})
        self.assertNotIn("link_target_id", by_id[3002]["dropdown"])
        self.assertEqual(demotion_warnings(plan), [])
        validate_plan(plan)
        validate_engine_plan(plan)


class DropdownLinkDemotionEngineTests(unittest.TestCase):
    """Engine level: a demoted record stays writable at its own address."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        body = (value_record(0, "1000")
                + value_record(1, "1040",
                               extra='<DropDownListLink>Ghost List</DropDownListLink>'))
        self.table = write_table(self.root, body)
        self.memory = Memory()
        self.engine = TrainerEngine(compile_table(self.table, PROCESS),
                                    state_dir=self.root / "state",
                                    process_lock_dir=self.root / "shared",
                                    memory_factory=lambda name: self.memory,
                                    hook_coordinator=Coordinator())
        self.engine.poll()
        self.assertTrue(self.engine.connected, self.engine.status)

    def tearDown(self):
        if getattr(self, "engine", None) is None:
            return
        self.memory.alive = False
        self.engine.poll()
        self.engine.close()

    def test_demoted_record_reads_and_writes_its_own_address(self):
        engine = self.engine
        self.assertEqual(engine.read_value(1), "0")
        self.assertEqual(engine.set_value(1, "1234"), "1234")
        # Decimal display for a plain 4 Bytes value: "1234" is the decimal
        # 1234 (0x4D2) in memory, not the hex value 0x1234.
        self.assertEqual(self.memory.read(0x1040, 4), struct.pack("<I", 1234))
        self.assertEqual(engine.read_value(1), "1234")


if __name__ == "__main__":
    unittest.main()
