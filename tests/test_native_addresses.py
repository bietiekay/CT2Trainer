"""Address inheritance and pointer flattening through first-party CT parsing."""

import copy
from pathlib import Path
import tempfile
import unittest

from ct2trainer.native.address_expression import resolve_expression
from ct2trainer.native.compiler import NativeCompileError, compile_table, validate_plan
from ct2trainer.native.engine import NativeRuntimeError, validate_plan as validate_runtime_plan


def record(identifier, address=None, *, children="", offsets=(), heading=False, script=None):
    address_xml = "" if address is None else f"<Address>{address}</Address>"
    offset_xml = "<Offsets>" + "".join(f"<Offset>{offset}</Offset>" for offset in offsets) + "</Offsets>" if offsets else ""
    type_xml = "<GroupHeader>1</GroupHeader>" if heading else "<VariableType>4 Bytes</VariableType>"
    if script is not None:
        type_xml = "<VariableType>Auto Assembler Script</VariableType><AssemblerScript>" + script + "</AssemblerScript>"
    return f'<CheatEntry><ID>{identifier}</ID><Description>"Record {identifier}"</Description>{type_xml}{address_xml}{offset_xml}' + (f"<CheatEntries>{children}</CheatEntries>" if children else "") + "</CheatEntry>"


class AddressPlanTests(unittest.TestCase):
    def compile(self, content, selected=None):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "owned.ct"
            path.write_text('<CheatTable CheatEngineTableVersion="45"><CheatEntries>' + content + '</CheatEntries></CheatTable>', encoding="utf-8")
            return compile_table(path, "owned.exe", selected_ids=selected)

    def test_nearest_address_header_and_nested_pointer_order(self):
        content = record(1, "1000", offsets=("20", "10"), heading=True,
                         children=record(2, heading=True, children=record(3, "+4", offsets=("8",))))
        plan = self.compile(content, [3])
        row = plan["entries"][2]
        self.assertTrue(row["supported"], row["reason"])
        self.assertEqual(row["address_profile"], "expression/v1")
        self.assertEqual(row["source_address"], "+4")
        self.assertEqual(row["pointer_offsets"], [])
        self.assertEqual(plan["selected_ids"], [1, 2, 3])

        class Memory:
            pointers = {0x1000: 0x2000, 0x2010: 0x3000, 0x3024: 0x4000}

            def read(self, address, size):
                self_size = size
                return self.pointers[address].to_bytes(self_size, "little")

        self.assertEqual(resolve_expression(row["address"], Memory()), 0x4008)

    def test_nested_relative_header_with_math(self):
        content = record(1, "1000", heading=True,
                         children=record(2, "+20", heading=True,
                                         children=record(3, "+4*2")))
        row = self.compile(content)["entries"][2]
        self.assertTrue(row["supported"], row["reason"])
        self.assertEqual(resolve_expression(row["address"], object()), 0x1028)

    def test_brackets_and_process_atoms(self):
        content = record(1, '[$process+100]+20', offsets=("8",))
        row = self.compile(content)["entries"][0]
        self.assertTrue(row["supported"], row["reason"])

        class Memory:
            def module(self, name):
                self_name = name
                if self_name != "owned.exe":
                    raise AssertionError(name)
                return 0x1000, 0x1000

            def read(self, address, size):
                return {0x1100: 0x2000, 0x2020: 0x3000}[address].to_bytes(size, "little")

        self.assertEqual(resolve_expression(row["address"], Memory(), process_name="owned.exe"), 0x3008)

    def test_symbol_dependencies_and_selection_follow_flattened_address(self):
        script = '[ENABLE]\ndefine(anchor,1000)\nregistersymbol(anchor)\n[DISABLE]\nunregistersymbol(anchor)'
        content = record(1, script=script) + record(2, "[anchor]+10", heading=True, children=record(3, "+4"))
        plan = self.compile(content, [3])
        row = plan["entries"][2]
        self.assertTrue(row["supported"], row["reason"])
        self.assertEqual(row["requires"], ["anchor"])
        self.assertEqual(row["dependency_ids"], [1])
        self.assertEqual(plan["selected_ids"], [1, 2, 3])

    def test_missing_or_addressless_nonheading_parent_blocks(self):
        for content in (record(1, "+4"), record(1, children=record(2, "+4")), record(1, "-4")):
            with self.subTest(content=content):
                row = self.compile(content)["entries"][-1]
                self.assertFalse(row["supported"])
                self.assertIn("Relative address", row["reason"])

    def test_addressless_heading_pointer_offsets_cannot_be_silently_dropped(self):
        content = record(1, "1000", heading=True,
                         children=record(2, heading=True, offsets=("20",),
                                         children=record(3, "+4")))
        row = self.compile(content)["entries"][-1]
        self.assertFalse(row["supported"])
        self.assertIn("addressless heading with pointer offsets", row["reason"])
        self.assertIn("ambiguous", row["reason"])

    def test_simple_address_profile_remains_unchanged(self):
        row = self.compile(record(1, '"owned.exe"+100', offsets=("20", "10")))["entries"][0]
        self.assertTrue(row["supported"])
        self.assertNotIn("address_profile", row)
        self.assertEqual(row["pointer_offsets"], [0x20, 0x10])

    def test_flattened_plan_validation_and_pointer_depth(self):
        plan = self.compile(record(1, "[1000]+10"))
        for key, value in (("address", "+1"), ("pointer_offsets", [1]), ("requires", ["unknown"]), ("address_profile", "arbitrary")):
            malformed = copy.deepcopy(plan)
            malformed["entries"][0][key] = value
            for validator, error in ((validate_plan, NativeCompileError),
                                     (validate_runtime_plan, NativeRuntimeError)):
                with self.subTest(key=key, validator=validator.__module__), self.assertRaises(error):
                    validator(malformed)
        missing_source = copy.deepcopy(plan)
        del missing_source["entries"][0]["source_address"]
        for validator, error in ((validate_plan, NativeCompileError),
                                 (validate_runtime_plan, NativeRuntimeError)):
            with self.subTest(key="source_address", validator=validator.__module__), self.assertRaises(error):
                validator(missing_source)
        row = self.compile(record(1, "[1000]", offsets=("0",) * 32))["entries"][0]
        self.assertFalse(row["supported"])
        self.assertIn("32 pointer", row["reason"])


if __name__ == "__main__":
    unittest.main()
