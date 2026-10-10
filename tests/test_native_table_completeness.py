"""Gate:1 evidence — per-table completeness for all 13 pinned tables.

For every pinned table the compiled plan must (a) preserve every source
record, and (b) account for every table-level construct the parser can see:
Forms, the table-Lua lifecycle, Custom Types and Assets (embedded Files).
This closes the "per-table completeness" gate that the feature matrix lists
as partial while the components are implemented but not demonstrated on the
pinned corpus.

No target process is spawned and no CE implementation is used; the corpus is
the clean-room synthetic set committed under TableReferences/.
"""
from __future__ import annotations

import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "TableReferences"
GAP_REPORT = ROOT / "gap_inventory" / "gap-report.json"

if not CORPUS.is_dir():
    raise unittest.SkipTest("synthetic corpus not present")

from ct2trainer.native.compiler import compile_table  # noqa: E402


def _pinned_tables():
    """(relative_path, architecture) tuples in gap-report order.

    ``architecture.value`` is a detector suggestion that may be "unknown";
    the completeness claim is record/construct coverage, so an undetermined
    architecture falls back to x64 (the controller default) rather than
    aborting the demonstration.
    """
    import json
    report = json.loads(GAP_REPORT.read_text(encoding="utf-8"))
    out = []
    for table in report["pinned_tables"]:
        arch = table["architecture"]["value"]
        if arch not in ("x86", "x64"):
            arch = "x64"
        out.append((Path(table["path"]), arch))
    return out


def _source_facts(ct_path: Path):
    """Ground truth read straight from the CT XML, independent of the compiler."""
    root = ET.fromstring(ct_path.read_bytes())
    ids = {el.findtext("ID") for el in root.iter("CheatEntry") if el.findtext("ID")}
    top_level = {child.tag for child in root}
    custom = 0
    for entry in root.iter("CheatEntry"):
        vtype = entry.findtext("VariableType")
        if vtype and vtype.strip().lower() == "custom":
            custom += 1
    return {
        "ids": ids,
        "has_lua": "LuaScript" in top_level,
        "has_forms": "Forms" in top_level,
        "has_custom_types": "CustomTypes" in top_level,
        "has_files": "Files" in top_level,
        "custom_record_count": custom,
    }


class PerTableCompletenessTests(unittest.TestCase):
    """Every pinned table compiles with every record and construct accounted for."""

    def test_all_pinned_tables_are_complete(self):
        tables = _pinned_tables()
        self.assertEqual(len(tables), 13, "expected the 13 pinned corpus tables")
        for rel, arch in tables:
            with self.subTest(table=str(rel)):
                ct = CORPUS / rel
                self.assertTrue(ct.is_file(), f"missing corpus table {rel}")
                facts = _source_facts(ct)
                plan = compile_table(str(ct), process_name="probe.exe", architecture=arch)

                # (a) No record is dropped: every source ID appears in the plan.
                plan_ids = {str(entry["id"]) for entry in plan["entries"]}
                self.assertTrue(
                    facts["ids"] <= plan_ids,
                    f"dropped records: {sorted(facts['ids'] - plan_ids)[:5]}",
                )
                self.assertEqual(
                    plan["counts"]["total"], len(facts["ids"]),
                    "plan entry count must equal source record count")

                # (b) Every table-level construct is accounted for.
                ignored = plan.get("ignored_sections", [])
                self.assertEqual(
                    ("Forms" in ignored), facts["has_forms"],
                    "Forms section presence mismatch")
                self.assertEqual(
                    ("Files" in ignored), facts["has_files"],
                    "Assets (Files) section presence mismatch")
                self.assertEqual(
                    ("CustomTypes" in ignored), facts["has_custom_types"],
                    "CustomTypes section presence mismatch")
                self.assertEqual(
                    ("lua_bootstrap" in plan), facts["has_lua"],
                    "table-Lua lifecycle mismatch")

                # Custom-typed records are present and consistently reported.
                plan_custom = [e for e in plan["entries"] if e.get("variable_type") == "Custom"]
                self.assertEqual(len(plan_custom), facts["custom_record_count"],
                                 "custom-typed record count mismatch")
                for entry in plan_custom:
                    self.assertTrue(
                        entry["supported"] or entry["reason"],
                        f"custom record {entry['id']} is neither supported nor explained")

    def test_corpus_has_no_embedded_files(self):
        """Assets gate: the pinned corpus carries no embedded Files section,
        so Assets completeness is demonstrated as a verified-absence claim."""
        tables = _pinned_tables()
        for rel, _arch in tables:
            facts = _source_facts(CORPUS / rel)
            with self.subTest(table=str(rel)):
                self.assertFalse(facts["has_files"],
                                 f"{rel} unexpectedly carries an embedded Files section")


class AssetsSectionRecognitionTests(unittest.TestCase):
    """A synthetic table with an embedded Files section is recognized, not lost."""

    def test_files_section_is_reported_ignored(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="ct2-assets-") as d:
            d = Path(d)
            ct = d / "assets.ct"
            ct.write_text(
                '<CheatTable CheatEngineTableVersion="7"><CheatEntries>'
                '<CheatEntry><ID>0</ID><Description>a</Description>'
                '<Address>401000</Address><VariableType>4 Bytes</VariableType>'
                "<Value>1</Value></CheatEntry>"
                "</CheatEntries>"
                "<Files><File>extra\\asset.bin</File></Files>"
                "</CheatTable>", encoding="utf-8")
            plan = compile_table(str(ct), process_name="probe.exe", architecture="x64")
            self.assertIn("Files", plan.get("ignored_sections", []),
                          "embedded Files (Assets) section must be recognized, not silently dropped")
            self.assertEqual(plan["counts"]["total"], 1)


if __name__ == "__main__":
    unittest.main()
