"""Gate:3 evidence — end-to-end reproducibility chain across all features.

Re-runs the exact documented command chain (denominator -> feature matrix ->
AP-11 manifest) against the pinned corpus and the committed upstream
artifacts, and requires the outputs to reproduce the committed
``gap_inventory`` artifacts byte-for-byte. This proves the full measurement
chain is deterministic from pinned inputs with exact commands.

Provenance fields are exact by construction: ``inventory.json`` records the
corpus path as given, and ``feature-coverage.json`` / ``ap11-campaign.json``
record the abspathed input locations. The byte-identity tests therefore feed
the exact input paths the committed artifacts were produced from (relative
``TableReferences`` corpus, committed gap_inventory files), and a final test
runs the chain fully from scratch in a temp tree and compares all content
with only the provenance fields stripped.

Pure analysis: no game process is spawned and no CE implementation is used.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "TableReferences"
GAP_DIR = ROOT / "gap_inventory"

if not CORPUS.is_dir():
    raise unittest.SkipTest("synthetic corpus not present")

PY = sys.executable


def _run_tool(script, args):
    proc = subprocess.run(
        [PY, str(ROOT / "tools" / "corpus_denominator" / script)] + list(args),
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (
        "%s failed (rc=%d): %s" % (script, proc.returncode, proc.stderr[-2000:])
    )
    return proc


def _committed_bytes(name):
    return (GAP_DIR / name).read_bytes()


def _strip_provenance(name, data):
    """Drop only the provenance fields that record where inputs lived."""
    if name in ("feature-coverage.json", "ap11-campaign.json"):
        data.pop("source", None)
    if name == "inventory.json":
        data.pop("corpus_root", None)
    return data


class ReproChainTests(unittest.TestCase):
    """The committed gap_inventory artifacts are exactly reproducible."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        report = json.loads(_committed_bytes("gap-report.json"))
        cls.run_id = report["run_id"]

    def _run_tool(self, script, args):
        return _run_tool(script, args)

    def test_01_denominator_reproduces_inventory_and_gap_report(self):
        tmp = tempfile.TemporaryDirectory(prefix="ct2-repro-chain-")
        self.addCleanup(tmp.cleanup)
        out1 = Path(tmp.name) / "stage1"
        # Relative corpus path: the committed inventory records it verbatim.
        self._run_tool(
            "__main__.py",
            ["--corpus", "TableReferences", "--output", str(out1),
             "--run-id", self.run_id],
        )
        self.assertEqual(
            (out1 / "inventory.json").read_bytes(), _committed_bytes("inventory.json"),
            "inventory.json is not byte-identical")
        self.assertEqual(
            (out1 / "gap-report.json").read_bytes(), _committed_bytes("gap-report.json"),
            "gap-report.json is not byte-identical")

    def test_02_feature_matrix_reproduces_feature_coverage(self):
        tmp = tempfile.TemporaryDirectory(prefix="ct2-repro-chain-")
        self.addCleanup(tmp.cleanup)
        out2 = Path(tmp.name) / "stage2"
        self._run_tool(
            "feature_matrix.py",
            ["--gap-report", str(GAP_DIR / "gap-report.json"),
             "--inventory", str(GAP_DIR / "inventory.json"),
             "--output", str(out2),
             "--run-id", self.run_id],
        )
        self.assertEqual(
            (out2 / "feature-coverage.json").read_bytes(),
            _committed_bytes("feature-coverage.json"),
            "feature-coverage.json is not byte-identical")

    def test_03_ap11_reproduces_campaign_manifest(self):
        tmp = tempfile.TemporaryDirectory(prefix="ct2-repro-chain-")
        self.addCleanup(tmp.cleanup)
        out3 = Path(tmp.name) / "stage3"
        self._run_tool(
            "ap11_campaign.py",
            ["manifest",
             "--gap-report", str(GAP_DIR / "gap-report.json"),
             "--inventory", str(GAP_DIR / "inventory.json"),
             "--feature-coverage", str(GAP_DIR / "feature-coverage.json"),
             "--corpus-root", str(CORPUS),
             "--output", str(out3),
             "--run-id", self.run_id],
        )
        self.assertEqual(
            (out3 / "ap11-campaign.json").read_bytes(),
            _committed_bytes("ap11-campaign.json"),
            "ap11-campaign.json is not byte-identical")

    def test_04_full_chain_from_scratch_is_content_identical(self):
        """Chain every stage from scratch in a temp tree.

        Stage 2 consumes stage 1's outputs and stage 3 consumes stage 2's
        feature-coverage, so the embedded provenance paths differ from the
        committed ones by construction. Everything except the provenance
        fields must be identical.
        """
        tmp = tempfile.TemporaryDirectory(prefix="ct2-repro-chain-")
        self.addCleanup(tmp.cleanup)
        out1 = Path(tmp.name) / "stage1"
        out2 = Path(tmp.name) / "stage2"
        out3 = Path(tmp.name) / "stage3"
        self._run_tool(
            "__main__.py",
            ["--corpus", "TableReferences", "--output", str(out1),
             "--run-id", self.run_id],
        )
        self._run_tool(
            "feature_matrix.py",
            ["--gap-report", str(out1 / "gap-report.json"),
             "--inventory", str(out1 / "inventory.json"),
             "--output", str(out2),
             "--run-id", self.run_id],
        )
        self._run_tool(
            "ap11_campaign.py",
            ["manifest",
             "--gap-report", str(out1 / "gap-report.json"),
             "--inventory", str(out1 / "inventory.json"),
             "--feature-coverage", str(out2 / "feature-coverage.json"),
             "--corpus-root", str(CORPUS),
             "--output", str(out3),
             "--run-id", self.run_id],
        )
        for name, produced in (
            ("inventory.json", out1 / "inventory.json"),
            ("gap-report.json", out1 / "gap-report.json"),
            ("feature-coverage.json", out2 / "feature-coverage.json"),
            ("ap11-campaign.json", out3 / "ap11-campaign.json"),
        ):
            with self.subTest(artifact=name):
                expected = _strip_provenance(name, json.loads(_committed_bytes(name)))
                actual = _strip_provenance(name, json.loads(produced.read_bytes()))
                self.assertEqual(actual, expected,
                                 name + " chain content differs from committed")


if __name__ == "__main__":
    unittest.main()
