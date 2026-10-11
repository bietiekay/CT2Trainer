"""Gate:2 evidence (parity half) — Source-to-Frozen parity of the 0.9 feature set.

The 0.9 feature set (custom types, table-Lua lifecycle, Auto Assembler
scripts, nth-of-block AOB) plus the WP-14 staged fields (staged metadata,
activation sets, parent relations, one-shot flags) must survive the source
-> frozen round-trip exactly. These tests compile real pinned corpus tables
that exercise those features, freeze them into a trainer via
``build_trainer`` (appended to a checked independent template), read the
plan back out of the produced EXE, and assert the frozen plan is byte- and
value-identical to the source-compiled plan. The frozen runtime (launcher
smoke) is then shown to read the same plan.

No game process is touched; the template is an inert owned PE stub.
"""
from __future__ import annotations

import hashlib
import json
import struct
import tempfile
import unittest
from pathlib import Path

from ct2trainer.native.bundle import build_trainer, read_embedded_plan, canonical_bytes
from ct2trainer.native.compiler import compile_table
from ct2trainer.native import launcher

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "TableReferences"

if not CORPUS.is_dir():
    raise unittest.SkipTest("synthetic corpus not present")

# Pinned tables chosen to exercise the 0.9 feature set:
#   case-06.ct (origin: Resident Evil 2)  -> custom types + table-Lua lifecycle + AA scripts
#   case-07.ct (origin: Borderlands 3)    -> Forms + large entry set + AA
#   case-14.ct (origin: PRAGMATA, WP-14)  -> staged values, script-parent flag
#       classes, lua-static activation sets, one-shot AA, signed offsets
_PARITY_TABLES = (
    ("case-06.ct", "x64", "ct2synth06.exe"),
    ("case-07.ct", "x64", "ct2synth07.exe"),
    ("case-14.ct", "x64", "ct2synth14.exe"),
)


def _template(root: Path) -> Path:
    path = root / "template.exe"
    stub = bytearray(128)
    stub[:2] = b"MZ"
    struct.pack_into("<I", stub, 0x3C, 64)
    stub[64:68] = b"PE\0\0"
    struct.pack_into("<H", stub, 68, 0x8664)
    path.write_bytes(stub + hashlib.sha256(stub).digest() + b"CT2BASE1")
    return path


class SourceFrozenParityTests(unittest.TestCase):
    """A 0.9-feature plan is byte-identical after the freeze round-trip."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ct2-parity-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.template = _template(self.root)

    def _parity(self, rel, arch, process):
        source = compile_table(str(CORPUS / rel), process, architecture=arch)
        exe, report = build_trainer(source, self.root / "trainer.exe",
                                    self.template)
        frozen = read_embedded_plan(exe)

        # Value parity: the frozen plan is the exact source plan.
        self.assertEqual(frozen, source, "frozen plan differs from source plan")
        # Byte parity: the canonical encoding the runtime trusts is stable.
        self.assertEqual(canonical_bytes(frozen), canonical_bytes(source),
                         "canonical plan bytes differ between source and frozen")

        # The build report is bound to the same plan identity.
        metadata = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual(metadata["table_sha256"], source["table_sha256"])
        self.assertEqual(metadata["entries"], len(source["entries"]))

        # The frozen runtime reads back and smokes the same plan.
        plan_file = self.root / "frozen.json"
        plan_file.write_text(json.dumps(frozen), encoding="utf-8")
        smoke = self.root / "smoke.json"
        rc = launcher.main(["--plan", str(plan_file),
                            "--smoke-output", str(smoke)])
        self.assertEqual(rc, 0)
        smoke_data = json.loads(smoke.read_text(encoding="utf-8"))
        self.assertEqual(smoke_data["trainer_id"], source["trainer_id"])
        self.assertEqual(smoke_data["entries"], len(source["entries"]))
        self.assertFalse(smoke_data["ce_payload"])

    def test_re2_feature_set_round_trips(self):
        self._parity("case-06.ct", "x64", "ct2synth06.exe")

    def test_borderlands3_feature_set_round_trips(self):
        self._parity("case-07.ct", "x64",
                     "ct2synth07.exe")

    def test_case14_feature_set_round_trips(self):
        self._parity("case-14.ct", "x64", "ct2synth14.exe")

    def test_case14_staged_metadata_round_trips(self):
        """WP-14 staged fields survive the freeze byte- and value-identically.

        If canonical_bytes or the frozen plan path dropped any staged field
        (staged metadata, activation sets, parent relations, one-shot flags),
        the frozen plan would differ from the source plan for the same entry
        ids; that is a product bug and is reported, not worked around.
        """
        source = compile_table(str(CORPUS / "case-14.ct"), "ct2synth14.exe",
                               architecture="x64")
        exe, _report = build_trainer(source, self.root / "trainer.exe",
                                     self.template)
        frozen = read_embedded_plan(exe)

        # Byte parity of the canonical plan bytes the runtime trusts.
        self.assertEqual(canonical_bytes(frozen), canonical_bytes(source),
                         "canonical frozen plan bytes differ from source")

        # Plan-level staged structure.
        self.assertEqual(frozen.get("parent_relations"),
                         source.get("parent_relations"),
                         "parent_relations differ between source and frozen")

        # Value parity for the staged fields, per entry id.
        frozen_by_id = {entry["id"]: entry for entry in frozen["entries"]}
        diffs = []
        for entry in source["entries"]:
            other = frozen_by_id.get(entry["id"])
            if other is None:
                diffs.append("entry %s missing from frozen plan" % entry["id"])
                continue
            for field in ("staged", "activation_sets", "one_shot"):
                if entry.get(field) != other.get(field):
                    diffs.append("entry %s %s: %r != %r" % (
                        entry["id"], field, entry.get(field),
                        other.get(field)))
        self.assertEqual(diffs, [],
                         "staged metadata lost in freeze: "
                         + "; ".join(diffs[:5]))

        # The exact staged record set of case-14 is intact in the frozen plan.
        source_staged = {entry["id"]: entry["staged"]
                         for entry in source["entries"] if "staged" in entry}
        frozen_staged = {entry["id"]: entry["staged"]
                         for entry in frozen["entries"] if "staged" in entry}
        self.assertEqual(len(source_staged), 33,
                         "case-14 must stage exactly 33 records")
        self.assertEqual(set(source_staged), set(frozen_staged),
                         "staged record set changed in freeze")
        for entry_id in sorted(source_staged):
            self.assertEqual(frozen_staged[entry_id], source_staged[entry_id],
                             "staged metadata differs for entry %s"
                             % entry_id)

    def test_09_features_present_in_source_plan(self):
        plan = compile_table(str(CORPUS / "case-06.ct"), "ct2synth06.exe",
                             architecture="x64")
        self.assertIn("lua_bootstrap", plan)
        self.assertTrue(any(e.get("variable_type") == "Custom"
                            for e in plan["entries"]),
                        "0.9 custom-typed records must be present")
        self.assertTrue(any(e.get("kind") == "script" for e in plan["entries"]),
                        "0.9 Auto Assembler records must be present")


if __name__ == "__main__":
    unittest.main()
