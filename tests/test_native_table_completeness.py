"""Gate:1 evidence - per-table completeness for all 20 pinned tables.

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
        self.assertEqual(len(tables), 20, "expected the 20 pinned corpus tables")
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


# WP-14 case-14 (origin: PRAGMATA behaviour derivative) is the staged
# capabilities table: 57 records, table version 46, 0 blocked.  The
# per-table loop above proves the generic invariants for it; the class
# below pins the record-level WP-14 semantics.
CASE_14 = "case-14.ct"
CASE_14_PROCESS = "ct2synth14.exe"
CASE_14_STAGED_IDS = (
    3, 4, 5,                # under script parent 2
    7,                      # under script parent 6
    9, 10,                  # under script parent 8
    12, 13,                 # under script parent 11
    15, 17, 18, 19, 20, 22, 24,  # under script parent 14
    23,                     # nested AA under value 22, symbol from 21
    26,                     # inventory base under script parent 25
    *range(38, 54),         # inventory _ID/_Quantity pairs under 25
)


class Case14CompletenessTests(unittest.TestCase):
    """Gate:1 evidence for the 14th pinned table (WP-14 staged capabilities)."""

    @classmethod
    def setUpClass(cls):
        ct = CORPUS / CASE_14
        if not ct.is_file():
            raise unittest.SkipTest("case-14 corpus table not present")
        cls.plan = compile_table(str(ct), process_name=CASE_14_PROCESS,
                                 architecture="x64")
        cls.entries = {str(entry["id"]): entry for entry in cls.plan["entries"]}

    def test_all_57_source_records_preserved(self):
        """Every source CheatEntry id maps to a plan entry; none is lost."""
        facts = _source_facts(CORPUS / CASE_14)
        self.assertEqual(len(facts["ids"]), 57,
                         "case-14 must carry exactly 57 source records")
        self.assertEqual(facts["ids"], set(self.entries),
                         "dropped or extra records: "
                         f"{sorted(facts['ids'] ^ set(self.entries))[:8]}")
        self.assertEqual(self.plan["counts"]["total"], 57,
                         "plan entry count must equal source record count")
        self.assertEqual(self.plan["counts"]["supported"], 57)
        self.assertEqual(self.plan["counts"]["blocked"], 0)

    def test_nested_aa_under_value_parent_is_handled(self):
        """AA scripts nested under value records are supported, not lost."""
        for rid in ("21", "23"):
            entry = self.entries[rid]
            with self.subTest(record=rid):
                self.assertEqual(entry["kind"], "script")
                self.assertTrue(entry["supported"],
                                f"nested AA {rid} is not supported: "
                                f"{entry['reason']}")
                self.assertNotEqual(entry["kind"], "blocked")
        # Record 23 shares the `skip_overwrite` label registered by 21.
        self.assertEqual(self.entries["23"]["requires"], ["skip_overwrite"])
        self.assertEqual(self.entries["23"]["dependency_ids"], [21])

    def test_staged_leaves_carry_provider_metadata(self):
        """Exactly 33 staged leaves; labels come from the provider path."""
        staged = {str(entry["id"]): entry["staged"]
                  for entry in self.plan["entries"] if "staged" in entry}
        self.assertEqual(set(staged), {str(rid) for rid in CASE_14_STAGED_IDS},
                         "staged record set mismatch")
        self.assertEqual(len(staged), 33)
        for eid in sorted(staged, key=int):
            meta = staged[eid]
            with self.subTest(record=eid):
                self.assertEqual(set(meta.keys()),
                                 {"provider_ids", "provider_labels"})
                self.assertTrue(meta["provider_ids"])
                self.assertEqual(
                    meta["provider_labels"],
                    [self.entries[str(pid)]["path"]
                     for pid in meta["provider_ids"]],
                    "provider labels must be the provider entry paths")

    def test_script_parent_flag_classes(self):
        """Records 2/11/14/25 exercise all three script-parent flag classes."""
        relations = self.plan["parent_relations"]
        for pid, expected in (("2", "required_dependency"),
                              ("11", "direct_activation"),
                              ("14", "collective_off"),
                              ("25", "required_dependency")):
            entry = self.entries[pid]
            with self.subTest(parent=pid):
                self.assertTrue(entry["supported"])
                self.assertEqual(entry.get("parent_activation"), expected)
                children = relations.get(pid)
                self.assertIsInstance(children, dict)
                self.assertTrue(children)
                self.assertTrue(
                    all(flag == expected for flag in children.values()))
        self.assertEqual({int(k) for k in relations["2"]}, {3, 4, 5})
        self.assertEqual({int(k) for k in relations["11"]}, {12, 13})
        self.assertEqual({int(k) for k in relations["14"]}, set(range(15, 25)))
        self.assertEqual({int(k) for k in relations["25"]}, set(range(26, 54)))
        # The staged children toggle normally with dependency auto-enable.
        for eid, provider in ((3, 2), (12, 11), (15, 14), (26, 25)):
            with self.subTest(record=eid):
                self.assertEqual(
                    self.entries[str(eid)]["staged"]["provider_ids"],
                    [provider])

    def test_activation_set_extracted_on_master_toggle(self):
        entry = self.entries["0"]
        self.assertEqual(entry["kind"], "script")
        self.assertTrue(entry["supported"])
        self.assertEqual(
            entry["activation_sets"],
            {"enable": [2, 6, 8, 11, 14, 25],
             "disable": [2, 6, 8, 11, 14, 25],
             "source": "lua-static-extract"})
        others = [e["id"] for e in self.plan["entries"]
                  if "activation_sets" in e and e["id"] != 0]
        self.assertEqual(others, [],
                         "activation sets must live only on the master toggle")

    def test_signed_offset_resolution(self):
        """+0x130 on record 7; +28 inside heading 16's own pointer chain."""
        rec7 = self.entries["7"]
        self.assertTrue(rec7["supported"])
        self.assertEqual(rec7["pointer_offsets"], [304])
        heading = self.entries["16"]
        self.assertEqual(heading["kind"], "heading")
        self.assertTrue(heading["supported"])
        # The heading's own chain (address +18, offset +28) resolves into the
        # flattened address of its first leaf child.
        child = self.entries["17"]
        self.assertEqual(child["address"],
                         "([[([EnhanceManager_addr])+18]+28])+60")

    def test_one_shot_record_56(self):
        entry = self.entries["56"]
        self.assertEqual(entry["kind"], "script")
        self.assertTrue(entry["supported"],
                        f"one-shot record 56 not supported: {entry['reason']}")
        self.assertTrue(entry["one_shot"])
        self.assertEqual(entry["enable"], [
            {"op": "assert", "address": "ct2synth14.exe+40", "bytes": "41"},
            {"op": "write", "address": "ct2synth14.exe+40", "bytes": "48"},
        ])
        self.assertEqual(entry["disable"], [])


if __name__ == "__main__":
    unittest.main()
