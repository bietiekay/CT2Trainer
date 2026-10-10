"""Integration wiring tests for static custom types across table, capability, compiler and lua_host."""

import tempfile
import unittest
from pathlib import Path

from ct2trainer.capability import assess
from ct2trainer.native.compiler import compile_table
from ct2trainer.native.custom_types import ABORT_SCHEMA, CustomTypeError
from ct2trainer.native.lua_host import LuaHost, LuaHostError
from ct2trainer.table import read_table


def _ct_xml(custom_types_section: str, entries: str) -> str:
    return (
        '<CheatTable CheatEngineTableVersion="45">'
        + custom_types_section
        + '<CheatEntries>' + entries + '</CheatEntries>'
        + '</CheatTable>'
    )


CUSTOM_TYPES_SECTION = (
    '<CustomTypes>'
    '<CustomType name="Hours">1</CustomType>'
    '<CustomType name="Mins" Inverse="1">2</CustomType>'
    '</CustomTypes>'
)

ENTRY_KNOWN = (
    '<CheatEntry><ID>1</ID><Description>"Known"</Description>'
    '<VariableType>Custom</VariableType><CustomType>Hours</CustomType>'
    '<Address>Target.exe+1000</Address></CheatEntry>'
)

ENTRY_UNKNOWN = (
    '<CheatEntry><ID>2</ID><Description>"Unknown"</Description>'
    '<VariableType>Custom</VariableType><CustomType>Ghost</CustomType>'
    '<Address>Target.exe+2000</Address></CheatEntry>'
)


def _write_ct(xml_text: str, tmpdir: str, name: str = "test.ct") -> Path:
    path = Path(tmpdir) / name
    path.write_text(xml_text, encoding="utf-8")
    return path


class CustomTypeWiringTableTests(unittest.TestCase):
    def test_static_custom_types_parsed_and_entries_resolved(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_ct(_ct_xml(CUSTOM_TYPES_SECTION, ENTRY_KNOWN + ENTRY_UNKNOWN), tmp)
            table = read_table(path)

            self.assertTrue(table.has_custom_types)
            self.assertTrue(table.has_custom_type_records)
            self.assertEqual([p.name for p in table.custom_types], ["Hours", "Mins"])
            self.assertEqual(table.custom_types[0].size, 1)
            self.assertEqual(table.custom_types[1].size, 2)
            self.assertTrue(table.custom_types[1].inverse)

            by_id = {e.id: e for e in table.entries}
            self.assertTrue(by_id[1].custom_type_known)
            self.assertFalse(by_id[2].custom_type_known)

    def test_unparseable_custom_types_section_stays_visible(self):
        broken = '<CustomTypes><CustomType name="Bad">9</CustomType></CustomTypes>'
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_ct(_ct_xml(broken, ENTRY_KNOWN), tmp)
            table = read_table(path)

            self.assertTrue(table.has_custom_types)
            self.assertEqual(table.custom_types, ())
            self.assertFalse(table.entries[0].custom_type_known)
            self.assertTrue(
                any("does not parse" in w for w in table.warnings),
                f"Expected a visible parse-error warning, got: {table.warnings}",
            )

    def test_no_custom_types_section_is_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_ct(_ct_xml("", ENTRY_KNOWN), tmp)
            table = read_table(path)
            self.assertFalse(table.has_custom_types)
            self.assertEqual(table.custom_types, ())

    def test_to_dict_exposes_custom_type_profiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_ct(_ct_xml(CUSTOM_TYPES_SECTION, ENTRY_KNOWN), tmp)
            table = read_table(path)
            payload = table.to_dict()
            self.assertIn("custom_types", payload)
            self.assertEqual(payload["custom_types"][0]["name"], "Hours")
            self.assertEqual(payload["custom_types"][1]["inverse"], True)
            self.assertTrue(payload["entries"][0]["custom_type_known"])


class CustomTypeWiringCapabilityTests(unittest.TestCase):
    def test_statically_defined_custom_records_use_fine_reasons(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_ct(_ct_xml(CUSTOM_TYPES_SECTION, ENTRY_KNOWN), tmp)
            table = read_table(path)
            report = assess(table)

            self.assertIn("custom-types-statically-defined", report["table_review_reasons"])
            self.assertIn("custom-type-records-statically-defined", report["table_review_reasons"])
            self.assertNotIn("custom-type-records-require-ce-test", report["table_review_reasons"])

            entry = [r for r in report["entries"] if r["id"] == 1][0]
            self.assertIn("custom-type-statically-defined", entry["review_reasons"])
            self.assertNotIn("custom-type-definition-runtime-required", entry["review_reasons"])

    def test_lua_defined_custom_records_keep_original_reasons(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_ct(_ct_xml("", ENTRY_UNKNOWN), tmp)
            table = read_table(path)
            report = assess(table)

            self.assertIn("custom-type-records-require-ce-test", report["table_review_reasons"])

            entry = [r for r in report["entries"] if r["id"] == 2][0]
            self.assertIn("custom-type-definition-runtime-required", entry["review_reasons"])


class CustomTypeWiringCompilerTests(unittest.TestCase):
    def _compile(self, custom_types: str, entries: str, selected: list[int] | None = None):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_ct(_ct_xml(custom_types, entries), tmp)
            return compile_table(path, "Target.exe", selected_ids=selected)

    def test_known_custom_record_blocked_with_named_reason(self):
        plan = self._compile(CUSTOM_TYPES_SECTION, ENTRY_KNOWN, selected=[1])
        entry = plan["entries"][0]
        self.assertFalse(entry["supported"])
        self.assertIn("statically defined", entry["reason"])
        self.assertIn("write gate", entry["reason"])

    def test_undefined_custom_record_blocked_with_named_reason(self):
        plan = self._compile("", ENTRY_UNKNOWN, selected=[2])
        entry = plan["entries"][0]
        self.assertFalse(entry["supported"])
        self.assertIn("no static definition", entry["reason"])


class CustomTypeWiringLuaHostTests(unittest.TestCase):
    def setUp(self):
        try:
            import lupa.lua53  # noqa: F401
        except ImportError:
            self.skipTest("pinned MIT Lupa Lua53 dependency is not installed")

    def test_custom_type_error_surfaces_as_named_json_abort(self):
        error = CustomTypeError(
            "span too short", code="custom-span-mismatch", stage="decode", offset=2
        )

        class Broker:
            generation = 0

            def call(self, name, args, *, generation, syntaxcheck):
                raise error

        host = LuaHost(Broker())
        with self.assertRaises(LuaHostError) as caught:
            host.execute("local v = readInteger(0x1000)")

        exc = caught.exception
        self.assertIsNotNone(getattr(exc, "abort_payload", None))
        self.assertEqual(exc.abort_payload, error.to_abort().to_dict())
        self.assertEqual(exc.abort_payload["schema"], ABORT_SCHEMA)
        self.assertEqual(exc.abort_payload["code"], "custom-span-mismatch")
        self.assertNotIn("Traceback", str(exc))

    def test_controller_work_converts_custom_type_error(self):
        error = CustomTypeError(
            "value out of range", code="custom-value-out-of-range", stage="encode", offset=1
        )

        class Broker:
            generation = 0
            def call(self, name, args, *, generation, syntaxcheck):
                return None

        host = LuaHost(Broker())
        with self.assertRaises(LuaHostError) as caught:
            with host.controller_work():
                raise error

        exc = caught.exception
        self.assertIsNotNone(getattr(exc, "abort_payload", None))
        self.assertEqual(exc.abort_payload, error.to_abort().to_dict())

    def test_normal_error_has_no_abort_payload(self):
        class Broker:
            generation = 0
            def call(self, name, args, *, generation, syntaxcheck):
                raise ValueError("boom")

        host = LuaHost(Broker())
        with self.assertRaises(LuaHostError) as caught:
            host.execute("local v = readInteger(0x1000)")

        self.assertIsNone(getattr(caught.exception, "abort_payload", None))
        self.assertEqual(str(caught.exception), "boom")


if __name__ == "__main__":
    unittest.main()
