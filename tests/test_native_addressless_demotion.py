"""WP-32: addressless value records demote to non-actionable placeholders.

A value record (simple type or actionable value profile) that carries no
address cannot anchor a write.  Instead of a blocked record it compiles to
a supported navigation heading with the exact reason
"Addressless value record is a non-actionable table placeholder." and no
address, profile, offsets, dependencies or dropdown metadata.  Zero-length
profile placeholders keep their own profile reason (they already demote).
Pointer offsets on an addressless record are refused fail-closed.  Children
with relative addresses that need the missing base stay blocked; children
with absolute addresses stay supported.  The plan validators pin the
demoted shape and refuse any tamper; the engine refuses value actions on
the demoted heading with its reason.
"""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from test_native_engine_code import Coordinator
from test_native_lua_activation import Memory
from ct2trainer.native.compiler import (NativeCompileError, compile_table,
                                        validate_plan)
from ct2trainer.native.engine import (NativeRuntimeError, TrainerEngine,
                                      validate_plan as validate_runtime_plan)

REASON = ("Addressless value record is a non-actionable "
          "table placeholder.")


class AddresslessDemotionCompileTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def compile(self, body):
        table = self.root / "addressless.ct"
        table.write_text('<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
                         + body + '</CheatEntries></CheatTable>', encoding="utf-8")
        return compile_table(table, "FixtureTarget.exe")

    def test_simple_types_demote_to_supported_placeholder_headings(self):
        bodies = {
            "Byte": '<VariableType>Byte</VariableType>',
            "2 Bytes": '<VariableType>2 Bytes</VariableType>',
            "4 Bytes": '<VariableType>4 Bytes</VariableType>',
            "8 Bytes": '<VariableType>8 Bytes</VariableType>',
            "Float": '<VariableType>Float</VariableType>',
            "Double": '<VariableType>Double</VariableType>',
            "Hex Float": '<VariableType>Float</VariableType><ShowAsHex>1</ShowAsHex>',
        }
        for name, variable in bodies.items():
            with self.subTest(name=name):
                plan = self.compile(
                    f'<CheatEntry><ID>1</ID><Description>{name}</Description>'
                    f'{variable}</CheatEntry>')
                entry = plan["entries"][0]
                self.assertEqual(entry["kind"], "heading")
                self.assertTrue(entry["supported"])
                self.assertEqual(entry["reason"], REASON)
                self.assertEqual(entry["source_kind"], "value")
                self.assertEqual(entry["source_address"], "")
                self.assertEqual(entry["address"], "")
                self.assertEqual(entry["variable_type"], name if name != "Hex Float" else "Float")
                self.assertNotIn("value_profile", entry)
                self.assertEqual(entry["pointer_offsets"], [])
                self.assertEqual(entry["requires"], [])
                self.assertEqual(entry["provides"], [])
                self.assertEqual(entry["dependency_ids"], [])
                self.assertEqual(entry["dropdown"],
                                 {"choices": [], "read_only": False})
                self.assertEqual(plan["counts"],
                                 {"total": 1, "supported": 1, "actionable": 0,
                                  "blocked": 0, "headings": 1})
                validate_plan(plan)
                validate_runtime_plan(plan)

    def test_actionable_profiles_demote_and_drop_the_profile(self):
        bodies = {
            "byte array": ('<VariableType>Array of byte</VariableType>'
                           '<ByteLength>4</ByteLength><ShowAsHex>1</ShowAsHex>'),
            "bit field": ('<VariableType>Binary</VariableType>'
                          '<BitStart>0</BitStart><BitLength>4</BitLength>'),
            "string": ('<VariableType>String</VariableType>'
                       '<Length>8</Length><ZeroTerminate>1</ZeroTerminate>'),
        }
        for name, variable in bodies.items():
            with self.subTest(name=name):
                plan = self.compile(
                    f'<CheatEntry><ID>1</ID><Description>{name}</Description>'
                    f'{variable}</CheatEntry>')
                entry = plan["entries"][0]
                self.assertEqual(entry["kind"], "heading")
                self.assertTrue(entry["supported"])
                self.assertEqual(entry["reason"], REASON)
                self.assertNotIn("value_profile", entry)
                self.assertEqual(entry["dropdown"],
                                 {"choices": [], "read_only": False})
                validate_plan(plan)
                validate_runtime_plan(plan)

    def test_zero_length_profile_placeholder_keeps_its_own_reason(self):
        # With an address: the existing zero-length profile demotion path
        # (profile reason, profile retained).
        plan = self.compile(
            '<CheatEntry><ID>1</ID><Description>Zero Array</Description>'
            '<VariableType>Array of byte</VariableType><Address>1040</Address>'
            '<ByteLength>0</ByteLength><ShowAsHex>1</ShowAsHex></CheatEntry>')
        entry = plan["entries"][0]
        self.assertEqual(entry["kind"], "heading")
        self.assertTrue(entry["supported"])
        self.assertEqual(entry["reason"],
                         "Zero-length byte array is a non-actionable table placeholder.")
        self.assertEqual(entry["value_profile"]["size"], 0)
        self.assertEqual(entry["address"], "1040")
        # Without an address: the profile path still wins (it runs first);
        # the addressless reason must not replace it.
        plan = self.compile(
            '<CheatEntry><ID>1</ID><Description>Zero Array</Description>'
            '<VariableType>Array of byte</VariableType>'
            '<ByteLength>0</ByteLength><ShowAsHex>1</ShowAsHex></CheatEntry>')
        entry = plan["entries"][0]
        self.assertEqual(entry["kind"], "heading")
        self.assertEqual(entry["reason"],
                         "Zero-length byte array is a non-actionable table placeholder.")
        self.assertEqual(entry["value_profile"]["size"], 0)
        self.assertEqual(entry["address"], "")
        validate_plan(plan)
        validate_runtime_plan(plan)

    def test_addressless_pointer_offsets_refused_fail_closed(self):
        plan = self.compile(
            '<CheatEntry><ID>1</ID><Description>NoBase</Description>'
            '<VariableType>4 Bytes</VariableType>'
            '<Offsets><Offset>10</Offset></Offsets></CheatEntry>')
        entry = plan["entries"][0]
        self.assertFalse(entry["supported"])
        self.assertEqual(entry["reason"],
                         "An addressless placeholder cannot carry pointer offsets.")

    def test_relative_child_of_demoted_parent_stays_blocked(self):
        plan = self.compile(
            '<CheatEntry><ID>1</ID><Description>NoBase</Description>'
            '<VariableType>4 Bytes</VariableType>'
            '<CheatEntries><CheatEntry><ID>2</ID><Description>Relative Kid</Description>'
            '<VariableType>Byte</VariableType><Address>+10</Address></CheatEntry>'
            '</CheatEntries></CheatEntry>')
        parent, child = plan["entries"]
        self.assertEqual(parent["kind"], "heading")
        self.assertTrue(parent["supported"])
        self.assertEqual(parent["reason"], REASON)
        self.assertFalse(child["supported"])
        self.assertEqual(child["reason"],
                         "Relative address cannot skip an addressless script/value ancestor.")

    def test_absolute_child_of_demoted_parent_stays_supported(self):
        plan = self.compile(
            '<CheatEntry><ID>1</ID><Description>NoBase</Description>'
            '<VariableType>4 Bytes</VariableType>'
            '<CheatEntries><CheatEntry><ID>2</ID><Description>Absolute Kid</Description>'
            '<VariableType>Byte</VariableType><Address>1040</Address></CheatEntry>'
            '</CheatEntries></CheatEntry>')
        parent, child = plan["entries"]
        self.assertEqual(parent["kind"], "heading")
        self.assertTrue(child["supported"], child["reason"])
        self.assertEqual(child["kind"], "value")
        self.assertEqual(child["address"], "1040")
        validate_plan(plan)
        validate_runtime_plan(plan)

    def test_validator_rejects_tampered_demoted_shape(self):
        from ct2trainer.native.value_types import prepare_value_profile
        plan = self.compile(
            '<CheatEntry><ID>1</ID><Description>NoBase</Description>'
            '<VariableType>4 Bytes</VariableType></CheatEntry>')
        cases = (
            ("reason changed",
             lambda entry: entry.update(reason="tampered"),
             "Value-type placeholder headings require canonical value metadata."),
            ("profile added",
             lambda entry: entry.update(value_profile=prepare_value_profile(
                 "Array of byte", {"ByteLength": 4, "ShowAsHex": True})),
             "Value profile type/display flags do not match the record."),
            ("address filled",
             lambda entry: entry.update(address="1040"),
             "Invalid addressless placeholder heading."),
            ("offsets filled",
             lambda entry: entry.update(pointer_offsets=[0x10]),
             "Invalid addressless placeholder heading."),
            ("requires filled",
             lambda entry: entry.update(requires=["SomeSymbol"]),
             "Invalid addressless placeholder heading."),
            ("provides filled",
             lambda entry: entry.update(provides=["SomeSymbol"]),
             "Invalid addressless placeholder heading."),
            ("dependency ids filled",
             lambda entry: entry.update(dependency_ids=[9]),
             "Invalid addressless placeholder heading."),
            ("dropdown filled",
             lambda entry: entry.update(dropdown={
                 "choices": [{"value": "1", "description": "x"}],
                 "read_only": False}),
             "Invalid addressless placeholder heading."),
        )
        for name, mutate, expected in cases:
            with self.subTest(name=name):
                tampered = deepcopy(plan)
                mutate(tampered["entries"][0])
                with self.assertRaises(NativeCompileError) as compile_error:
                    validate_plan(deepcopy(tampered))
                self.assertEqual(str(compile_error.exception), expected)
                with self.assertRaises(NativeRuntimeError) as runtime_error:
                    validate_runtime_plan(deepcopy(tampered))
                self.assertEqual(str(runtime_error.exception), expected)


class AddresslessDemotionEngineTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.table = self.root / "addressless.ct"
        self.table.write_text(
            '<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
            '<CheatEntry><ID>1</ID><Description>NoBase</Description>'
            '<VariableType>4 Bytes</VariableType></CheatEntry>'
            '<CheatEntry><ID>2</ID><Description>Anchor</Description>'
            '<VariableType>Byte</VariableType><Address>1040</Address></CheatEntry>'
            '</CheatEntries></CheatTable>', encoding="utf-8")
        self.memory = Memory()
        self.coordinator = Coordinator()
        self.plan = compile_table(self.table, "FixtureTarget.exe")
        validate_plan(self.plan)
        validate_runtime_plan(self.plan)
        self.engine = TrainerEngine(self.plan,
                                    state_dir=self.root / "state",
                                    process_lock_dir=self.root / "shared",
                                    memory_factory=lambda name: self.memory,
                                    hook_coordinator=self.coordinator)
        self.engine.poll()

    def tearDown(self):
        self.engine.close()

    def test_value_actions_refused_with_the_placeholder_reason(self):
        for operation in (lambda: self.engine.set_value(1, "1"),
                          lambda: self.engine.read_value(1),
                          lambda: self.engine.set_freeze(1, True)):
            with self.assertRaisesRegex(NativeRuntimeError,
                                        "non-actionable table placeholder"):
                operation()
        self.assertFalse(self.memory.writes)

    def test_sibling_absolute_record_stays_writable(self):
        self.assertEqual(self.engine.set_value(2, "7"), "7")
        self.assertEqual(self.memory.read(0x1040, 1), b"\x07")


if __name__ == "__main__":
    unittest.main()
