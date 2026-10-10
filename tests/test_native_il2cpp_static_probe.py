"""Gate:2 evidence — binary CLI/GUI adapter for the static IL2CPP parser.

Verifies that the static IL2CPP analyzer (``ct2trainer.native.il2cpp_static``)
is reachable from BOTH the source CLI (``ct2trainer native il2cpp``) and the
frozen trainer entry point (``launcher.main`` with ``--il2cpp-static-pe``),
producing a deterministic, bounded, read-only report.

Pure static analysis: no target process is spawned, no injection performed,
no target memory is written. This is the gate that lifts "static IL2CPP
parser reachable only from source" to "exposed through a binary CLI adapter".
"""
from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

_TEST_DIR = Path(__file__).resolve().parent
if str(_TEST_DIR) not in sys.path:
    sys.path.insert(0, str(_TEST_DIR))

from native_il2cpp_static_fixtures import metadata_fixture, pe_fixture  # noqa: E402
from ct2trainer.native import il2cpp_static_probe as probe_mod
from ct2trainer.native import launcher, __main__ as cli


def _fixture_files(tmpdir: Path):
    pe = tmpdir / "GameAssembly.dll"
    meta = tmpdir / "global-metadata.dat"
    pe.write_bytes(pe_fixture(64))
    meta.write_bytes(metadata_fixture())
    return pe, meta


class ProbeReportTests(unittest.TestCase):
    """run_probe produces a bounded, deterministic, read-only report."""

    def test_report_schema_and_pe_identity(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="ct2-il2cpp-probe-") as d:
            pe, meta = _fixture_files(Path(d))
            rep = probe_mod.run_probe(pe, meta)
            self.assertEqual(rep["schema"], "ct2trainer-il2cpp-static-probe/v1")
            self.assertEqual(rep["pe"]["bitness"], 64)
            self.assertEqual(rep["pe"]["section_count"], 1)
            self.assertEqual(rep["pe"]["sections"][0]["name"], ".own")
            self.assertEqual(rep["pe"]["image_base"], "0x180000000")
            # SHA-256 of the exact fixture bytes is stable and deterministic.
            import hashlib
            self.assertEqual(rep["pe"]["sha256"],
                             hashlib.sha256(pe_fixture(64)).hexdigest())

    def test_report_methods_are_bounded_and_deterministic(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="ct2-il2cpp-probe-") as d:
            pe, meta = _fixture_files(Path(d))
            r1 = probe_mod.run_probe(pe, meta)
            r2 = probe_mod.run_probe(pe, meta)
            self.assertEqual(r1, r2)  # deterministic
            self.assertEqual(r1["metadata"]["method_count"], 2)
            self.assertEqual(len(r1["methods"]), 2)
            self.assertEqual(r1["methods"][0]["class_name"], "Counter")
            self.assertTrue(r1["methods"][0]["is_static"])

    def test_report_writes_file_and_matches_return(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="ct2-il2cpp-probe-") as d:
            pe, meta = _fixture_files(Path(d))
            out = Path(d) / "report.json"
            rep = probe_mod.run_probe(pe, meta, out)
            self.assertTrue(out.exists())
            on_disk = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(on_disk, rep)

    def test_invalid_pe_raises_format_error(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="ct2-il2cpp-probe-") as d:
            d = Path(d)
            pe, meta = _fixture_files(d)
            bad = d / "bad.dll"
            bad.write_bytes(b"not a pe file at all")
            with self.assertRaises(probe_mod.FormatError):
                probe_mod.run_probe(bad, meta)

    def test_oversized_input_rejected_by_bound(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="ct2-il2cpp-probe-") as d:
            d = Path(d)
            pe, meta = _fixture_files(d)
            # Shrink the bound locally to exercise the size guard cheaply.
            original = probe_mod.MAX_PE_BYTES
            try:
                probe_mod.MAX_PE_BYTES = 1  # force the bound to trip
                with self.assertRaises(ValueError):
                    probe_mod.run_probe(pe, meta)
            finally:
                probe_mod.MAX_PE_BYTES = original


class CLISourceAdapterTests(unittest.TestCase):
    """``ct2trainer.native.il2cpp`` subcommand (source CLI adapter)."""

    def test_cli_il2cpp_writes_report(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="ct2-il2cpp-cli-") as d:
            d = Path(d)
            pe, meta = _fixture_files(d)
            out = d / "report.json"
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cli.main(["il2cpp", str(pe), "--metadata", str(meta),
                               "--output", str(out)])
            self.assertEqual(rc, 0)
            self.assertTrue(out.exists())
            rep = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(rep["schema"], probe_mod.SCHEMA)
            self.assertEqual(rep["pe"]["bitness"], 64)

    def test_cli_il2cpp_requires_metadata(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="ct2-il2cpp-cli-") as d:
            d = Path(d)
            pe, _ = _fixture_files(d)
            with self.assertRaises(SystemExit):
                cli.main(["il2cpp", str(pe)])  # --metadata is required


class FrozenBinaryAdapterTests(unittest.TestCase):
    """``launcher.main`` exposes the same analysis via ``--il2cpp-static-pe``.

    This is the "binary" side of the adapter: the frozen trainer entry point
    routes the flags to the same ``run_probe`` without needing a plan or a
    target process.
    """

    def test_launcher_il2cpp_gate_returns_zero_and_writes_report(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="ct2-il2cpp-launcher-") as d:
            d = Path(d)
            pe, meta = _fixture_files(d)
            report = d / "gate.json"
            rc = launcher.main([
                "--il2cpp-static-pe", str(pe),
                "--il2cpp-static-metadata", str(meta),
                "--il2cpp-static-report", str(report),
            ])
            self.assertEqual(rc, 0)
            rep = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(rep["schema"], probe_mod.SCHEMA)
            self.assertFalse(rep["process_access"])
            self.assertFalse(rep["target_writes"])

    def test_launcher_il2cpp_gate_requires_metadata_and_report(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="ct2-il2cpp-launcher-") as d:
            d = Path(d)
            pe, _ = _fixture_files(d)
            buf = io.StringIO()
            with redirect_stderr(buf):
                rc = launcher.main(["--il2cpp-static-pe", str(pe)])
            self.assertEqual(rc, 2)
            self.assertIn("required together", buf.getvalue())

    def test_il2cpp_gate_is_mutually_exclusive_with_other_gates(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="ct2-il2cpp-launcher-") as d:
            d = Path(d)
            pe, meta = _fixture_files(d)
            buf = io.StringIO()
            with redirect_stderr(buf):
                rc = launcher.main([
                    "--il2cpp-static-pe", str(pe),
                    "--il2cpp-static-metadata", str(meta),
                    "--il2cpp-static-report", str(d / "r.json"),
                    "--smoke",
                ])
            self.assertEqual(rc, 2)
            self.assertIn("Choose only one", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
