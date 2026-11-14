import json
import hashlib
from pathlib import Path
import struct
import tempfile
import unittest

from ct2trainer.native import bundle
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

    def test_signed_trainer_roundtrips_with_certificate_tail(self):
        # An Authenticode certificate table may legally sit after the plan
        # footer; the footer scan must find the plan through the tail.
        output, _ = build_trainer(self.plan, self.root / "signed.exe", self.template)
        base = output.read_bytes()
        output.write_bytes(base + b"\x30" * 0x100)
        self.assertEqual(read_embedded_plan(output), self.plan)

    def test_footer_magic_inside_certificate_tail_is_not_misread(self):
        # A magic occurrence inside the certificate tail with a plausible
        # length field but a failing checksum is skipped, never accepted.
        output, _ = build_trainer(self.plan, self.root / "signed.exe", self.template)
        base = output.read_bytes()
        tail = bytearray()
        tail += b"\x00" * 24
        tail += (16).to_bytes(8, "little")
        tail += b"CT2NATV1"
        tail += b"\xAA" * 64
        output.write_bytes(base + bytes(tail))
        self.assertEqual(read_embedded_plan(output), self.plan)

    def test_footer_scan_is_bounded_by_the_certificate_tail(self):
        # A tail beyond the bounded certificate window hides the footer;
        # the refusal is named and fail-closed.
        output, _ = build_trainer(self.plan, self.root / "signed.exe", self.template)
        base = output.read_bytes()
        output.write_bytes(base + b"\x00" * (bundle.MAX_CERTIFICATE_TAIL + 1))
        with self.assertRaisesRegex(ValueError, "Missing or invalid"):
            read_embedded_plan(output)

    def test_signing_is_applied_before_publication_and_reported(self):
        calls = []

        def fake_sign(path):
            calls.append(Path(path))
            return {"signed": True, "certificate": {"certificate_length": 72}}
        output, report = build_trainer(self.plan, self.root / "signed.exe",
                                       self.template, sign=fake_sign)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].parent, output.parent)
        self.assertTrue(output.read_bytes().startswith(self.template.read_bytes()))
        self.assertEqual(read_embedded_plan(output), self.plan)
        metadata = json.loads(report.read_text())
        self.assertTrue(metadata["signed"])

    def test_unsigned_build_is_the_default_and_reported(self):
        output, report = build_trainer(self.plan, self.root / "trainer.exe", self.template)
        metadata = json.loads(report.read_text())
        self.assertFalse(metadata["signed"])


if __name__ == "__main__":
    unittest.main()
