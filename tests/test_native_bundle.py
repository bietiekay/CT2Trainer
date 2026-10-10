import json
import hashlib
from pathlib import Path
import struct
import tempfile
import unittest

from ct2trainer.native.bundle import build_trainer, read_embedded_plan
from ct2trainer.native.compiler import compile_table

ROOT = Path(__file__).resolve().parents[1]


class NativeBundleTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.template = self.root / "template.exe"
        stub = bytearray(128)
        stub[:2] = b"MZ"
        struct.pack_into("<I", stub, 0x3C, 64)
        stub[64:68] = b"PE\0\0"
        struct.pack_into("<H", stub, 68, 0x8664)
        self.template.write_bytes(stub + hashlib.sha256(stub).digest() + b"CT2BASE1")
        self.plan = compile_table(ROOT / "tests/windows/fixture_target/fixture.ct", "FixtureTarget.exe")

    def test_plan_roundtrip_and_report_are_bound_to_actual_output(self):
        output, report = build_trainer(self.plan, self.root / "trainer.exe", self.template)
        self.assertEqual(read_embedded_plan(output), self.plan)
        self.assertTrue(output.read_bytes().startswith(self.template.read_bytes()))
        metadata = json.loads(report.read_text())
        self.assertFalse(metadata["ce_payload"])
        self.assertEqual(metadata["table_sha256"], self.plan["table_sha256"])

    def test_changed_or_truncated_plan_is_rejected(self):
        output, _ = build_trainer(self.plan, self.root / "trainer.exe", self.template)
        data = bytearray(output.read_bytes())
        data[len(self.template.read_bytes()) + 1] ^= 1
        output.write_bytes(data)
        with self.assertRaisesRegex(ValueError, "checksum"):
            read_embedded_plan(output)
        output.write_bytes(data[:-5])
        with self.assertRaises(ValueError):
            read_embedded_plan(output)

    def test_existing_output_is_not_replaced_without_force(self):
        output, _ = build_trainer(self.plan, self.root / "trainer.exe", self.template)
        before = output.read_bytes()
        with self.assertRaises(FileExistsError):
            build_trainer(self.plan, output, self.template)
        self.assertEqual(output.read_bytes(), before)

    def test_invalid_template_architecture_is_rejected(self):
        stub = bytearray(self.template.read_bytes())
        struct.pack_into("<H", stub, 68, 0x014C)
        stub[-40:-8] = hashlib.sha256(stub[:-40]).digest()
        self.template.write_bytes(stub)
        with self.assertRaisesRegex(ValueError, "x64"):
            build_trainer(self.plan, self.root / "trainer.exe", self.template)

    def test_arbitrary_pe_stub_is_not_claimed_to_be_ce_free(self):
        self.template.write_bytes(self.template.read_bytes()[:-40])
        with self.assertRaisesRegex(ValueError, "checked independent"):
            build_trainer(self.plan, self.root / "trainer.exe", self.template)

    def test_overlay_length_is_bounded(self):
        output, _ = build_trainer(self.plan, self.root / "trainer.exe", self.template)
        data = bytearray(output.read_bytes())
        struct.pack_into("<Q", data, len(data) - 16, 2**63)
        output.write_bytes(data)
        with self.assertRaises(ValueError):
            read_embedded_plan(output)


if __name__ == "__main__":
    unittest.main()
