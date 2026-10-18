"""Runtime dynamic address provider wiring (WP-38, GC-B6).

Corpus semantics (synthetic fixture, no original table content): an
addressless script record that proves statically that it registers one
symbol on enable and unregisters it on disable is a dynamic address
provider.  Relative value children whose ancestor walk is interrupted by
that script keep their raw relative address; the nearest heading records
the provider binding in the additive plan field ``address_provider`` and
the engine resolves the inherited base fresh from the runtime symbol table
at every activation.  Both plan gates refuse forged marker metadata with
named errors, the runtime refuses with the exact provider phrase while the
provider is not live, and the marker is the only UI-facing surface.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import re
import struct
import tempfile
import unittest

from test_native_engine_code import Coordinator
from test_native_lua_activation import Memory
from ct2trainer.native.compiler import (NativeCompileError, compile_table,
                                        validate_plan as validate_source_plan)
from ct2trainer.native.engine import (NativeRuntimeError, TrainerEngine,
                                      validate_plan as validate_engine_plan)
from ct2trainer.native.ui_layout import address_provider_marker

SKIP_REASON = "Relative address cannot skip an addressless script/value ancestor."
ADOPTED_REASON = ("Native relative value; the inherited base is resolved "
                  "at runtime from the dynamic address provider.")
INACTIVE = "Address provider 3000 is not active."
INACTIVE_RE = re.escape(INACTIVE)

PROVIDER_SOURCE = (
    "[ENABLE]\n{$lua}\nif not syntaxcheck then\n"
    "registerSymbol('BaseAddr', readQword('0x1008'))\nend\n{$asm}\n"
    "[DISABLE]\n{$lua}\nunregisterSymbol('BaseAddr')\n{$asm}")

PROVIDER_FAIL_SOURCE = (
    "[ENABLE]\n{$lua}\nif not syntaxcheck then\n"
    "registerSymbol('BaseAddr', readQword('0x2000'))\nend\n{$asm}\n"
    "[DISABLE]\n{$lua}\nunregisterSymbol('BaseAddr')\n{$asm}")

PROVIDER_TWO_SYMBOLS_SOURCE = (
    "[ENABLE]\n{$lua}\nif not syntaxcheck then\n"
    "registerSymbol('BaseAddr', readQword('0x1008'))\n"
    "registerSymbol('OtherAddr', readQword('0x100c'))\nend\n{$asm}\n"
    "[DISABLE]\n{$lua}\nunregisterSymbol('BaseAddr')\n"
    "unregisterSymbol('OtherAddr')\n{$asm}")

PROVIDER_NO_RELEASE_SOURCE = (
    "[ENABLE]\n{$lua}\nif not syntaxcheck then\n"
    "registerSymbol('BaseAddr', readQword('0x1008'))\nend\n{$asm}\n"
    "[DISABLE]\n{$lua}\n-- release is owned elsewhere\n{$asm}")


def write_table(root: Path, provider_source: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    table = root / "provider.ct"
    table.write_text(
        '<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
        '<CheatEntry><ID>3000</ID><Description>"Dynamic base"'
        '</Description><VariableType>Auto Assembler Script</VariableType>'
        '<AssemblerScript>{provider}</AssemblerScript>'
        '<CheatEntries>'
        '<CheatEntry><ID>3001</ID><Description>"Provider group"'
        '</Description><GroupHeader>1</GroupHeader>'
        '<CheatEntries>'
        '<CheatEntry><ID>3002</ID><Description>"First"</Description>'
        '<VariableType>4 Bytes</VariableType><Address>+10</Address></CheatEntry>'
        '<CheatEntry><ID>3003</ID><Description>"Second"</Description>'
        '<VariableType>4 Bytes</VariableType><Address>+14</Address></CheatEntry>'
        '<CheatEntry><ID>3004</ID><Description>"Third"</Description>'
        '<VariableType>Byte</VariableType><Address>+18</Address></CheatEntry>'
        '</CheatEntries>'
        '</CheatEntry>'
        '</CheatEntries>'
        '</CheatEntry>'
        '<CheatEntry><ID>3010</ID><Description>"Sibling"</Description>'
        '<VariableType>4 Bytes</VariableType><Address>1060</Address></CheatEntry>'
        '</CheatEntries></CheatTable>'.replace("{provider}", provider_source),
        encoding="utf-8")
    return table


class DynamicAddressProviderPlanTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.table = write_table(self.root, PROVIDER_SOURCE)
        self.plan = compile_table(self.table, "FixtureTarget.exe")
        self.by_id = {entry["id"]: entry for entry in self.plan["entries"]}

    def test_plan_carries_the_provider_binding_on_the_nearest_heading(self):
        heading = self.by_id[3001]
        self.assertEqual(heading["kind"], "heading")
        self.assertTrue(heading["supported"])
        self.assertEqual(heading["address"], "")
        self.assertEqual(heading["pointer_offsets"], [])
        self.assertEqual(heading["address_provider"],
                         {"provider_id": 3000, "symbol": "BaseAddr"})
        provider = self.by_id[3000]
        self.assertEqual(provider["kind"], "script")
        self.assertTrue(provider["supported"], provider["reason"])
        self.assertEqual(provider["address"], "")
        self.assertEqual(provider["pointer_offsets"], [])
        self.assertEqual(provider["provides"], ["BaseAddr"])
        self.assertEqual(provider["requires"], [])
        self.assertIn("lua_program", provider)
        self.assertNotIn("address_provider", provider)
        for record_id, address in ((3002, "+10"), (3003, "+14"), (3004, "+18")):
            child = self.by_id[record_id]
            self.assertEqual(child["kind"], "value", child["reason"])
            self.assertTrue(child["supported"], child["reason"])
            self.assertEqual(child["address"], address)
            self.assertEqual(child["source_address"], address)
            self.assertEqual(child["address_profile"], "expression/v1")
            self.assertEqual(child["pointer_offsets"], [])
            self.assertEqual(child["requires"], [])
            self.assertEqual(child["dependency_ids"], [])
            self.assertNotIn("staged", child)
            self.assertNotIn("address_provider", child)
            self.assertEqual(child["reason"], ADOPTED_REASON)
        # The runtime-computed base is never baked into any plan record.
        self.assertFalse(
            any(entry.get("address") == "1020"
                or entry.get("source_address") == "1020"
                for entry in self.plan["entries"]))
        self.assertEqual(self.plan["selected_ids"],
                         [3000, 3001, 3002, 3003, 3004, 3010])

    def test_both_plan_gates_accept_the_valid_plan(self):
        validate_source_plan(self.plan)
        validate_engine_plan(self.plan)

    def _forge(self, mutate, message, trimmed=None, selected_ids=None):
        plan = deepcopy(self.plan)
        by_id = {entry["id"]: entry for entry in plan["entries"]}
        if trimmed is not None:
            plan["entries"] = [entry for entry in plan["entries"]
                               if entry["id"] in trimmed]
            plan["selected_ids"] = list(selected_ids)
            for entry in plan["entries"]:
                entry["selected"] = True
        mutate(by_id)
        with self.assertRaisesRegex(NativeCompileError, message):
            validate_source_plan(plan)
        with self.assertRaisesRegex(NativeRuntimeError, message):
            validate_engine_plan(plan)

    def test_forged_marker_metadata_is_rejected_by_both_gates(self):
        marker = {"provider_id": 3000, "symbol": "BaseAddr"}
        # A non-heading record cannot carry the marker.
        self._forge(lambda by_id: by_id[3000].update(address_provider=dict(marker)),
                    "Dynamic address provider requires a supported addressless heading\\.")
        self._forge(lambda by_id: (by_id[3001].pop("address_provider"),
                                   by_id[3002].update(address_provider=dict(marker))),
                    "Dynamic address provider requires a supported addressless heading\\.")
        # A heading with its own address is not addressless.
        self._forge(lambda by_id: by_id[3001].update(address="1200"),
                    "Dynamic address provider requires a supported addressless heading\\.")
        # A malformed marker value is refused before any cross-check.
        self._forge(lambda by_id: by_id[3001].update(address_provider="BaseAddr"),
                    "Invalid dynamic address provider metadata\\.")
        # A marker symbol outside the symbol grammar.
        self._forge(lambda by_id: by_id[3001]["address_provider"].update(symbol="9bad"),
                    "Symbol must contain ASCII letters, digits or underscores\\.")
        # A named provider that does not exist (no relative children: the
        # dedicated unknown-record path is reached, not the value check).
        self._forge(lambda by_id: by_id[3001]["address_provider"].update(provider_id=9999),
                    "Dynamic address provider references an unknown record\\.",
                    trimmed={3000, 3001, 3010}, selected_ids=[3000, 3001, 3010])
        # A provider that exists but is not an addressless script.
        self._forge(lambda by_id: by_id[3001]["address_provider"].update(provider_id=3010),
                    "Dynamic address provider must name a supported addressless script record\\.",
                    trimmed={3000, 3001, 3010}, selected_ids=[3000, 3001, 3010])
        self._forge(lambda by_id: by_id[3000].update(address="1200"),
                    "Dynamic address provider must name a supported addressless script record\\.",
                    trimmed={3000, 3001, 3010}, selected_ids=[3000, 3001, 3010])
        # A provider that does not export the named symbol.
        self._forge(lambda by_id: by_id[3001]["address_provider"].update(symbol="Other"),
                    "Dynamic address provider does not provide the named symbol\\.",
                    trimmed={3000, 3001, 3010}, selected_ids=[3000, 3001, 3010])
        # A provider nested below the heading it serves (base cycle).
        self._forge(lambda by_id: by_id[3000].update(parent_id=3001),
                    "Dynamic address provider must not be a descendant of the heading it serves\\.",
                    trimmed={3000, 3001, 3010}, selected_ids=[3000, 3001, 3010])

    def test_forged_provider_binding_breaks_the_value_adoption(self):
        # With relative children present, an unresolvable binding is refused
        # by the per-record value check before the plan-wide cross-check.
        self._forge(lambda by_id: by_id[3001]["address_provider"].update(provider_id=9999),
                    "Expression-profile addresses must have resolved inherited bases\\.")


class DynamicAddressProviderRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.table = write_table(self.root, PROVIDER_SOURCE)
        self.memory = Memory()
        self.memory.data[8:16] = struct.pack("<Q", 0x1020)
        self.engine = TrainerEngine(compile_table(self.table, "FixtureTarget.exe"),
                                    state_dir=self.root / "state",
                                    process_lock_dir=self.root / "shared",
                                    memory_factory=lambda name: self.memory,
                                    hook_coordinator=Coordinator())
        self.engine.poll()
        self.assertTrue(self.engine.connected, self.engine.status)

    def tearDown(self):
        if getattr(self, "engine", None) is None:
            return
        self.memory.alive = False
        self.engine.poll()
        self.engine.close()

    def test_relative_values_refuse_with_the_exact_phrase_before_activation(self):
        engine = self.engine
        # The absolute sibling is unaffected and stays fully usable.
        self.assertEqual(engine.read_value(3010), "0")
        self.assertEqual(engine.set_value(3010, "7"), "7")
        self.assertEqual(self.memory.read(0x1060, 4), b"\x07\x00\x00\x00")
        writes = len(self.memory.writes)
        for record_id in (3002, 3003, 3004):
            with self.assertRaisesRegex(NativeRuntimeError, INACTIVE_RE):
                engine.read_value(record_id)
            with self.assertRaisesRegex(NativeRuntimeError, INACTIVE_RE):
                engine.set_value(record_id, "1")
            with self.assertRaisesRegex(NativeRuntimeError, INACTIVE_RE):
                engine.set_freeze(record_id, True)
            self.assertEqual(engine.entry_errors[record_id], INACTIVE)
        self.assertEqual(len(self.memory.writes), writes)
        self.assertFalse(engine.blocked)
        self.assertNotIn(3000, engine.desired)

    def test_provider_activation_resolves_children_freshly_and_reversibly(self):
        engine = self.engine
        self.assertTrue(engine.toggle(3000, True))
        self.assertEqual(engine.symbols["baseaddr"], 0x1020)
        self.assertIn(3000, engine.desired)
        self.assertEqual(engine.read_value(3002), "0")
        self.assertEqual(engine.set_value(3002, "1234"), "1234")
        self.assertEqual(self.memory.read(0x1030, 4), struct.pack("<I", 1234))
        self.assertEqual(engine.set_value(3003, "7"), "7")
        self.assertEqual(self.memory.read(0x1034, 4), b"\x07\x00\x00\x00")
        self.assertEqual(engine.set_value(3004, "255"), "255")
        self.assertEqual(self.memory.read(0x1038, 1), b"\xff")
        self.assertEqual(engine.read_value(3002), "1234")
        self.assertEqual(engine.read_value(3004), "255")
        # A frozen provider-bound value keeps its live base on every poll.
        self.assertTrue(engine.set_freeze(3003, True))
        self.memory.data[0x34] = 0xFF
        engine.poll()
        self.assertFalse(engine.blocked, engine.error)
        self.assertEqual(self.memory.read(0x1034, 4), b"\x07\x00\x00\x00")
        # Disabling the provider drops the symbol; the children refuse.
        engine.toggle(3000, False)
        self.assertNotIn("baseaddr", engine.symbols)
        self.assertNotIn(3000, engine.desired)
        with self.assertRaisesRegex(NativeRuntimeError, INACTIVE_RE) as ctx:
            engine.read_value(3002)
        self.assertFalse(engine.blocked)
        engine.set_freeze(3003, False)
        engine.poll()
        self.assertFalse(engine.blocked, engine.error)

    def test_failed_provider_enable_never_saves_a_wish(self):
        # The setUp engine shares self.memory; retire it before re-attaching.
        self.engine.close()
        self.engine = None
        self.memory.closed = False
        table = write_table(self.root / "fail", PROVIDER_FAIL_SOURCE)
        self.table = table
        self.engine = TrainerEngine(compile_table(table, "FixtureTarget.exe"),
                                    state_dir=self.root / "state-fail",
                                    process_lock_dir=self.root / "shared-fail",
                                    memory_factory=lambda name: self.memory,
                                    hook_coordinator=Coordinator())
        self.engine.poll()
        self.assertTrue(self.engine.connected, self.engine.status)
        with self.assertRaises(NativeRuntimeError):
            self.engine.toggle(3000, True)
        self.assertNotIn(3000, self.engine.desired)
        self.assertEqual(len(self.memory.writes), 0)
        self.assertFalse(self.engine.blocked)
        # The adopted children keep their exact runtime refusal.
        with self.assertRaisesRegex(NativeRuntimeError, INACTIVE_RE) as ctx:
            self.engine.read_value(3002)
        # The absolute sibling stays usable.
        self.assertEqual(self.engine.set_value(3010, "9"), "9")
        self.assertEqual(self.memory.read(0x1060, 4), b"\x09\x00\x00\x00")

    def test_re_attach_rebases_the_provider_from_live_memory(self):
        engine = self.engine
        self.assertTrue(engine.toggle(3000, True))
        self.assertEqual(engine.symbols["baseaddr"], 0x1020)
        self.memory.alive = False
        engine.poll()
        self.assertIsNone(engine.memory)
        replacement = Memory(pid=123, creation_time=999)
        replacement.data[8:16] = struct.pack("<Q", 0x1040)
        self.memory = replacement
        engine.poll()
        self.assertTrue(engine.connected, engine.status)
        # The saved wish re-enabled the provider against the new base.
        self.assertEqual(engine.symbols["baseaddr"], 0x1040)
        self.assertEqual(engine.set_value(3003, "5"), "5")
        self.assertEqual(replacement.read(0x1054, 4), b"\x05\x00\x00\x00")
        self.assertEqual(engine.read_value(3002), "0")
        engine.poll()
        self.assertFalse(engine.blocked, engine.error)


class DynamicAddressProviderNonQualifyingTests(unittest.TestCase):
    """Providers that fail the one-proven-export rule keep the named block."""

    def _compile(self, provider_source):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        table = write_table(root, provider_source)
        plan = compile_table(table, "FixtureTarget.exe")
        by_id = {entry["id"]: entry for entry in plan["entries"]}
        validate_source_plan(plan)
        validate_engine_plan(plan)
        self.assertFalse(any("address_provider" in entry
                             for entry in plan["entries"]))
        for record_id in (3002, 3003, 3004):
            child = by_id[record_id]
            self.assertEqual(child["kind"], "blocked", child["reason"])
            self.assertFalse(child["supported"])
            self.assertEqual(child["reason"], SKIP_REASON)
        return by_id

    def test_two_symbol_provider_keeps_the_named_block(self):
        by_id = self._compile(PROVIDER_TWO_SYMBOLS_SOURCE)
        self.assertEqual(by_id[3000]["provides"], ["BaseAddr", "OtherAddr"])

    def test_provider_without_release_keeps_the_named_block(self):
        by_id = self._compile(PROVIDER_NO_RELEASE_SOURCE)
        self.assertEqual(by_id[3000]["provides"], [])


class AddressProviderUiMarkerTests(unittest.TestCase):
    def test_marker_phrases_only_for_a_heading_with_the_plan_field(self):
        self.assertEqual(
            address_provider_marker(
                {"address_provider": {"provider_id": 3000, "symbol": "BaseAddr"}}),
            "Address provided at runtime")
        self.assertEqual(address_provider_marker({"kind": "heading"}), "")
        self.assertEqual(address_provider_marker({"address_provider": "BaseAddr"}), "")

    def test_marker_consumes_only_the_plan_field(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        plan = compile_table(write_table(root, PROVIDER_SOURCE), "FixtureTarget.exe")
        by_id = {entry["id"]: entry for entry in plan["entries"]}
        self.assertEqual(address_provider_marker(by_id[3001]),
                         "Address provided at runtime")
        for record_id in (3000, 3002, 3003, 3004, 3010):
            self.assertEqual(address_provider_marker(by_id[record_id]), "")


if __name__ == "__main__":
    unittest.main()
