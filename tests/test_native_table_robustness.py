"""WP-25 table robustness: keep-first duplicate CheatEntry IDs + legacy binary CT handling.

Fixture shapes mirror the planned case-19 corpus table (duplicate-ID pair where
one side is a group with children; a byte file with the 11-byte ``CHEATENGINE``
legacy binary magic header) on the owned module token ``ct2synth19.exe``.  The
pinned corpus case itself is added by the root integrator; the fixtures below
stay inside this test module.

Keep-first model (plan design note, decided 2026-10-13): the first occurrence
of an ID becomes the plan entry; later duplicates are dropped from the plan
(not emitted as addressable entries) and reported as one table warning per
duplicated ID.  Children of a dropped duplicate stay addressable at the
duplicate's own tree position (re-parented to the duplicate's parent), so the
plan total always equals the number of unique source IDs (gate:1 invariant
preserved).  Malformed XML without the legacy binary magic keeps its existing
``Invalid CT XML: ...`` reason byte-identically.

Since RT-3, files with the legacy binary magic load through the clean-room
reader (``ct2trainer.legacy_ct``) when parseable; unparseable legacy input is
refused with the named ``LegacyCTError`` (a ``TableError`` subclass), which
stays distinct from the ``Invalid CT XML`` reason.  The 96-byte fixture below
decodes as a version-9 table with 10 records whose bytes run out inside
record 2, so it pins the named truncation refusal; full happy-path coverage
lives in ``test_native_legacy_ct.py``.
"""

from __future__ import annotations

import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from ct2trainer.legacy_ct import LegacyCTError
from ct2trainer.native.compiler import NativeCompileError, compile_table
from ct2trainer.native.engine import validate_plan as validate_runtime_plan
from ct2trainer.table import TableError, read_table


PROCESS = "ct2synth19.exe"

# 96 bytes: 11-byte CHEATENGINE magic, version 9 (byte 11 is 0x09), record
# count 10 (byte 15 is 0x0A), then record 0 (description "Unlimited" padded
# to 15 bytes, zero address/flags) and record 1 (all-zero fields).  The
# parser reaches record 2's 4-byte description length at offset 94 with only
# 2 bytes left, so this fixture pins the named truncation refusal.  Full
# happy-path coverage of the legacy format lives in test_native_legacy_ct.py.
BINARY_HEADER_BODY = (
    b"CHEATENGINE\t\x00\x00\x00\n\x00\x00\x00\x0f"
    b"\x00\x00\x00Unlimited" + b"\x00" * 64
)

MISFORMED_XML = (
    '<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
    "<CheatEntry><ID>1</ID></CheatEntries></CheatTable>"
)

LEGACY_BINARY_MSG = (
    "Legacy binary CT table is truncated: record 2 description length "
    "needs 4 byte(s) at offset 94 but only 2 remain."
)


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
        f"<Address>{address}</Address></CheatEntry>"
    )


def group_entry(entry_id: int, description: str, children: str) -> str:
    return (
        f'<CheatEntry><ID>{entry_id}</ID>'
        f'<Description>{description}</Description>'
        "<GroupHeader>1</GroupHeader>"
        '<Options moHideChildren="1"/>'
        f"<CheatEntries>{children}</CheatEntries></CheatEntry>"
    )


def script_entry(entry_id: int, description: str, script: str) -> str:
    import xml.sax.saxutils

    return (
        f'<CheatEntry><ID>{entry_id}</ID>'
        f'<Description>{description}</Description>'
        "<VariableType>Auto Assembler Script</VariableType>"
        f"<AssemblerScript>{xml.sax.saxutils.escape(script)}</AssemblerScript>"
        "</CheatEntry>"
    )


def source_ids(path: Path) -> set[str]:
    """Ground truth unique-ID set, read independent of the parser."""
    root = ET.fromstring(path.read_bytes())
    return {el.findtext("ID") for el in root.iter("CheatEntry") if el.findtext("ID")}


class DuplicateIdKeepFirstTests(unittest.TestCase):
    """First occurrence owns the ID; later duplicates are dropped with a warning."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="ct2-wp25-dup-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def write_ct(self, name: str, body: str) -> Path:
        path = self.root / name
        path.write_text(table_xml(body), encoding="utf-8")
        return path

    def test_leaf_duplicate_keeps_first_and_warns_exactly(self):
        path = self.write_ct(
            "dup-leaf.ct",
            group_entry(1, "Group A", value_entry(2, "Alpha", "1000") + value_entry(3, "Beta", "1004"))
            + value_entry(2, "Alpha Copy", "2000"),
        )
        table = read_table(path)
        self.assertEqual([e.id for e in table.entries], [1, 2, 3])
        alpha = next(e for e in table.entries if e.id == 2)
        self.assertEqual(alpha.label, "Alpha")
        self.assertEqual(alpha.address, "1000")
        self.assertEqual(alpha.parent_id, 1)
        # exactly one addressable record per ID
        self.assertEqual(len(table.entries), 3)
        self.assertEqual({e.id for e in table.entries}, {1, 2, 3})
        self.assertEqual(len(source_ids(path)), 3)
        self.assertEqual(
            table.warnings,
            (
                "Duplicate CheatEntry ID: 2 (kept first occurrence; "
                "dropped 1 duplicate record(s): Alpha Copy)",
            ),
        )
        # plan level
        plan = compile_table(str(path), PROCESS, selected_ids=[2])
        self.assertEqual(plan["counts"]["total"], 3)
        plan_ids = [entry["id"] for entry in plan["entries"]]
        self.assertEqual(sorted(plan_ids), [1, 2, 3])
        by_id = {entry["id"]: entry for entry in plan["entries"]}
        self.assertEqual(len(by_id), 3)
        self.assertEqual(by_id[2]["label"], "Alpha")
        self.assertEqual(by_id[2]["parent_id"], 1)
        self.assertEqual(by_id[3]["parent_id"], 1)
        self.assertEqual(by_id[1]["kind"], "heading")
        self.assertEqual(by_id[1]["source_kind"], "heading")
        # selecting the kept record auto-includes its parent; the sibling
        # stays unselected — the dropped duplicate left no selection target.
        self.assertTrue(by_id[2]["selected"])
        self.assertTrue(by_id[1]["selected"])
        self.assertFalse(by_id[3]["selected"])
        validate_runtime_plan(plan)

    def test_group_first_then_leaf_duplicate(self):
        path = self.write_ct(
            "group-first.ct",
            group_entry(10, "Stat Group", value_entry(11, "HP", "2000") + value_entry(12, "SP", "2004"))
            + value_entry(10, "Stray", "3000"),
        )
        table = read_table(path)
        group = next(e for e in table.entries if e.id == 10)
        self.assertTrue(group.is_group_header)
        self.assertTrue(group.has_children)
        self.assertEqual(group.kind, "heading")
        self.assertEqual(
            table.warnings,
            (
                "Duplicate CheatEntry ID: 10 (kept first occurrence; "
                "dropped 1 duplicate record(s): Stray)",
            ),
        )
        plan = compile_table(str(path), PROCESS)
        self.assertEqual(plan["counts"]["total"], 3)
        by_id = {entry["id"]: entry for entry in plan["entries"]}
        self.assertEqual(by_id[11]["parent_id"], 10)
        self.assertEqual(by_id[12]["parent_id"], 10)
        self.assertEqual(by_id[10]["source_kind"], "heading")
        validate_runtime_plan(plan)

    def test_leaf_first_then_group_duplicate_reparents_children(self):
        """The dropped duplicate's unique-ID children are kept (not lost)."""
        path = self.write_ct(
            "leaf-first.ct",
            value_entry(20, "Base", "4000")
            + group_entry(20, "Group Copy", value_entry(21, "Child One", "4004") + value_entry(22, "Child Two", "4008")),
        )
        table = read_table(path)
        self.assertEqual([e.id for e in table.entries], [20, 21, 22])
        base = next(e for e in table.entries if e.id == 20)
        self.assertFalse(base.has_children)
        self.assertEqual(base.kind, "value")
        for kid in table.entries[1:]:
            self.assertIsNone(kid.parent_id)
        self.assertEqual(
            table.warnings,
            (
                "Duplicate CheatEntry ID: 20 (kept first occurrence; "
                "dropped 1 duplicate record(s): Group Copy)",
            ),
        )
        plan = compile_table(str(path), PROCESS)
        self.assertEqual(plan["counts"]["total"], 3)
        self.assertEqual({str(e["id"]) for e in plan["entries"]}, source_ids(path))
        by_id = {entry["id"]: entry for entry in plan["entries"]}
        self.assertIsNone(by_id[21]["parent_id"])
        self.assertIsNone(by_id[22]["parent_id"])
        validate_runtime_plan(plan)

    def test_nested_duplicate_groups_each_warn(self):
        """Mirrors the Octopath 4420/4421/4422 nested duplicate shape."""
        stats = value_entry(4421, "Extra HP", "5000") + value_entry(4422, "Extra SP", "5004")
        path = self.write_ct(
            "nested-4420.ct",
            group_entry(100, "Container", group_entry(4420, "Extra Stats", stats) + group_entry(4420, "Extra Stats", stats)),
        )
        table = read_table(path)
        self.assertEqual([e.id for e in table.entries], [100, 4420, 4421, 4422])
        self.assertEqual(
            table.warnings,
            (
                "Duplicate CheatEntry ID: 4420 (kept first occurrence; "
                "dropped 1 duplicate record(s): Extra Stats)",
                "Duplicate CheatEntry ID: 4421 (kept first occurrence; "
                "dropped 1 duplicate record(s): Extra HP)",
                "Duplicate CheatEntry ID: 4422 (kept first occurrence; "
                "dropped 1 duplicate record(s): Extra SP)",
            ),
        )
        plan = compile_table(str(path), PROCESS)
        self.assertEqual(plan["counts"]["total"], 4)
        self.assertEqual({str(e["id"]) for e in plan["entries"]}, source_ids(path))
        by_id = {entry["id"]: entry for entry in plan["entries"]}
        self.assertEqual(by_id[4420]["parent_id"], 100)
        self.assertEqual(by_id[4421]["parent_id"], 4420)
        self.assertEqual(by_id[4422]["parent_id"], 4420)
        validate_runtime_plan(plan)

    def test_unique_child_inside_dropped_subtree_is_kept(self):
        """A unique-ID child under a dropped duplicate must not be lost."""
        path = self.write_ct(
            "unique-child.ct",
            value_entry(30, "First", "6000")
            + group_entry(30, "Second", value_entry(31, "Only Once", "6004")),
        )
        table = read_table(path)
        self.assertEqual([e.id for e in table.entries], [30, 31])
        kept = next(e for e in table.entries if e.id == 31)
        self.assertIsNone(kept.parent_id)
        self.assertEqual(
            table.warnings,
            (
                "Duplicate CheatEntry ID: 30 (kept first occurrence; "
                "dropped 1 duplicate record(s): Second)",
            ),
        )
        plan = compile_table(str(path), PROCESS)
        self.assertEqual(plan["counts"]["total"], 2)
        self.assertEqual({str(e["id"]) for e in plan["entries"]}, source_ids(path))
        validate_runtime_plan(plan)

    def test_three_occurrences_warn_with_all_dropped_names(self):
        path = self.write_ct(
            "triple.ct",
            value_entry(40, "First", "7000")
            + value_entry(40, "Second", "7004")
            + value_entry(40, "Third", "7008"),
        )
        table = read_table(path)
        self.assertEqual([e.id for e in table.entries], [40])
        self.assertEqual(
            table.warnings,
            (
                "Duplicate CheatEntry ID: 40 (kept first occurrence; "
                "dropped 2 duplicate record(s): Second, Third)",
            ),
        )
        plan = compile_table(str(path), PROCESS)
        self.assertEqual(plan["counts"]["total"], 1)
        validate_runtime_plan(plan)

    def test_duplicate_script_record_keeps_first_and_compiles(self):
        script = (
            "[ENABLE]\nassert(ct2synth19.exe+10,00)\nct2synth19.exe+10:\ndb 01\n"
            "[DISABLE]\nassert(ct2synth19.exe+10,01)\nct2synth19.exe+10:\ndb 00"
        )
        path = self.write_ct(
            "dup-script.ct",
            script_entry(50, "Glow", script) + script_entry(50, "Glow Copy", script),
        )
        table = read_table(path)
        self.assertEqual([e.id for e in table.entries], [50])
        self.assertEqual(table.entries[0].label, "Glow")
        self.assertEqual(
            table.warnings,
            (
                "Duplicate CheatEntry ID: 50 (kept first occurrence; "
                "dropped 1 duplicate record(s): Glow Copy)",
            ),
        )
        plan = compile_table(str(path), PROCESS)
        entry = plan["entries"][0]
        self.assertEqual(entry["id"], 50)
        self.assertEqual(entry["label"], "Glow")
        self.assertEqual(entry["kind"], "script")
        self.assertTrue(entry["supported"])
        validate_runtime_plan(plan)

    def test_selection_with_unknown_id_still_refused(self):
        path = self.write_ct(
            "dup-leaf.ct",
            group_entry(1, "Group A", value_entry(2, "Alpha", "1000") + value_entry(3, "Beta", "1004"))
            + value_entry(2, "Alpha Copy", "2000"),
        )
        with self.assertRaises(NativeCompileError) as ctx:
            compile_table(str(path), PROCESS, selected_ids=[999])
        self.assertIn("unknown", str(ctx.exception))


class LegacyBinaryTableTests(unittest.TestCase):
    """The CHEATENGINE magic dispatches to the legacy binary reader.

    The 96-byte fixture below decodes as a version-9 table with 10 records
    whose bytes run out inside record 2, so it pins the named truncation
    refusal (``LegacyCTError``), which stays distinct from the
    ``Invalid CT XML`` reason of the XML path.  Fully valid legacy tables
    are covered by ``test_native_legacy_ct.py``.
    """

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="ct2-wp25-bin-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def test_truncated_legacy_binary_gets_named_distinct_error(self):
        path = self.root / "legacy.ct"
        path.write_bytes(BINARY_HEADER_BODY)
        with self.assertRaises(LegacyCTError) as ctx:
            read_table(path)
        self.assertEqual(str(ctx.exception), LEGACY_BINARY_MSG)
        self.assertFalse(str(ctx.exception).startswith("Invalid CT XML"))

    def test_truncated_legacy_binary_refusal_survives_compile_table(self):
        path = self.root / "legacy.ct"
        path.write_bytes(BINARY_HEADER_BODY)
        with self.assertRaises(LegacyCTError) as ctx:
            compile_table(str(path), PROCESS)
        self.assertEqual(str(ctx.exception), LEGACY_BINARY_MSG)

    def test_version_below_six_is_refused_as_too_old(self):
        path = self.root / "legacy-old.ct"
        path.write_bytes(
            b"CHEATENGINE" + (5).to_bytes(4, "little") + (1).to_bytes(4, "little"))
        with self.assertRaises(LegacyCTError) as ctx:
            read_table(path)
        self.assertEqual(
            str(ctx.exception),
            "Legacy binary CT table version 5 is older than 6; "
            "the pre-converter layout is not supported.",
        )


class MalformedXmlUnchangedTests(unittest.TestCase):
    """Malformed XML without the binary header keeps its existing reason."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="ct2-wp25-xml-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def test_malformed_xml_reason_is_byte_identical(self):
        path = self.root / "malformed.ct"
        path.write_text(MISFORMED_XML, encoding="utf-8")
        try:
            ET.fromstring(path.read_bytes())
        except ET.ParseError as exc:
            expected = f"Invalid CT XML: {exc}"
        with self.assertRaises(TableError) as ctx:
            read_table(path)
        self.assertEqual(str(ctx.exception), expected)
        self.assertTrue(str(ctx.exception).startswith("Invalid CT XML:"))
        # and it is distinct from the legacy binary reason
        self.assertNotEqual(str(ctx.exception), LEGACY_BINARY_MSG)


class SingleOccurrenceUnchangedTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="ct2-wp25-solo-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def test_unique_id_table_has_no_duplicate_warnings_and_compiles(self):
        path = self.root / "solo.ct"
        path.write_text(
            table_xml(value_entry(1, "Solo", "8000") + value_entry(2, "Solo Two", "8004")),
            encoding="utf-8",
        )
        table = read_table(path)
        self.assertEqual([e.id for e in table.entries], [1, 2])
        self.assertEqual(table.warnings, ())
        plan = compile_table(str(path), PROCESS)
        self.assertEqual(plan["counts"]["total"], 2)
        self.assertEqual(plan["counts"]["supported"], 2)
        validate_runtime_plan(plan)


if __name__ == "__main__":
    unittest.main()
