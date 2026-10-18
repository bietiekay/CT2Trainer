"""WP-40: record hotkey registration (first-wins) + original-binding display.

The synthetic CT mirrors the planned case-23 corpus shape (F1 enable,
F2 value operation, one first-wins conflict pair) plus every named
refusal class: value-operation hotkeys on non-actionable rows, activation
hotkeys on value rows, unsupported actions, unparseable key codes,
inactive (Active=0) bindings and value-step refusals for hex-float and
profile rows.  The plan carries every original binding byte-verifiably;
the engine publishes the live subset through the tested hotkey_model
controller with the first-wins conflict policy.
"""
from __future__ import annotations

from copy import deepcopy
import json
import struct
import tempfile
import unittest
from pathlib import Path

from test_native_lua_activation import Memory
from test_native_engine_code import Coordinator
from ct2trainer.native.compiler import compile_table, validate_plan as validate_source_plan
from ct2trainer.native.engine import (TrainerEngine, NativeRuntimeError,
                                      validate_plan as validate_engine_plan)
from ct2trainer.native.hotkey_model import HotKeySpec, ToggleOutcomeStatus
from ct2trainer.native.ui_layout import (LayoutError, hotkey_binding_line,
                                         hotkey_conflict_banner)


# Hex offsets are AA-relative to the scanned anchor (FakeMemory base 0x1000):
# +10 (value), +14/+18/+22 (script patch sites), +24 (hex float),
# +28 (byte array) are all zero-initial in the fixture memory.
CT_BODY = '''<?xml version="1.0" encoding="utf-8"?>
<CheatTable CheatEngineTableVersion="45">
  <CheatEntries>
    <CheatEntry>
      <ID>1</ID>
      <Description>"Hotkey anchor script"</Description>
      <VariableType>Auto Assembler Script</VariableType>
      <AssemblerScript>[ENABLE]
aobscanmodule(HotkeyAnchor,FixtureTarget.exe,43 54 32 54 2D 46 49 58 2D 32 30 32 36 2D 30 31)
registersymbol(HotkeyAnchor)
assert(HotkeyAnchor+14,00 00 00 00)
HotkeyAnchor+14:
  dd 1
[DISABLE]
unregistersymbol(HotkeyAnchor)
HotkeyAnchor+14:
  dd 0</AssemblerScript>
      <Hotkeys>
        <Hotkey Active="1">
          <Keys><Key>112</Key></Keys>
          <Action>Toggle Activation</Action>
        </Hotkey>
        <Hotkey Active="1">
          <Keys><Key>118</Key></Keys>
          <Action>Set Value</Action>
          <Value>5</Value>
        </Hotkey>
      </Hotkeys>
    </CheatEntry>
    <CheatEntry>
      <ID>2</ID>
      <Description>"Hotkey value (4 Bytes)"</Description>
      <VariableType>4 Bytes</VariableType>
      <Address>HotkeyAnchor+10</Address>
      <Hotkeys>
        <Hotkey Active="1">
          <Keys><Key>113</Key></Keys>
          <Action>Set Value</Action>
          <Value>999999</Value>
          <Description>Sets the value from the source table</Description>
        </Hotkey>
        <Hotkey Active="1">
          <Keys><Key>114</Key></Keys>
          <Action>Increase Value</Action>
          <Value>3</Value>
        </Hotkey>
        <Hotkey Active="1">
          <Keys><Key>116</Key></Keys>
          <Action>Toggle Activation</Action>
        </Hotkey>
        <Hotkey Active="1">
          <Keys><Key>122</Key></Keys>
          <Action>Increase Value</Action>
          <Value>abc</Value>
        </Hotkey>
        <Hotkey Active="1">
          <Keys><Key>123</Key></Keys>
          <Action>Set Value</Action>
          <Value></Value>
        </Hotkey>
      </Hotkeys>
    </CheatEntry>
    <CheatEntry>
      <ID>3</ID>
      <Description>"Conflicting F1 script"</Description>
      <VariableType>Auto Assembler Script</VariableType>
      <AssemblerScript>[ENABLE]
aobscanmodule(HotkeyAnchorB,FixtureTarget.exe,43 54 32 54 2D 46 49 58 2D 32 30 32 36 2D 30 31)
registersymbol(HotkeyAnchorB)
assert(HotkeyAnchorB+18,00 00 00 00)
HotkeyAnchorB+18:
  dd 1
[DISABLE]
unregistersymbol(HotkeyAnchorB)
HotkeyAnchorB+18:
  dd 0</AssemblerScript>
      <Hotkeys>
        <Hotkey Active="1">
          <Keys><Key>112</Key></Keys>
          <Action>Toggle Activation</Action>
        </Hotkey>
      </Hotkeys>
    </CheatEntry>
    <CheatEntry>
      <ID>4</ID>
      <Description>"Zero-length byte array placeholder"</Description>
      <VariableType>Array of byte</VariableType>
      <ByteLength>0</ByteLength>
      <Hotkeys>
        <Hotkey Active="1">
          <Keys><Key>115</Key></Keys>
          <Action>Set Value</Action>
          <Value>01</Value>
        </Hotkey>
      </Hotkeys>
    </CheatEntry>
    <CheatEntry>
      <ID>5</ID>
      <Description>"Inactive and unmappable hotkeys"</Description>
      <VariableType>Auto Assembler Script</VariableType>
      <AssemblerScript>[ENABLE]
aobscanmodule(HotkeyAnchorC,FixtureTarget.exe,43 54 32 54 2D 46 49 58 2D 32 30 32 36 2D 30 31)
registersymbol(HotkeyAnchorC)
assert(HotkeyAnchorC+22,00 00 00 00)
HotkeyAnchorC+22:
  dd 1
[DISABLE]
unregistersymbol(HotkeyAnchorC)
HotkeyAnchorC+22:
  dd 0</AssemblerScript>
      <Hotkeys>
        <Hotkey Active="0">
          <Keys><Key>117</Key></Keys>
          <Action>Toggle Activation</Action>
        </Hotkey>
        <Hotkey Active="1">
          <Keys><Key>31</Key></Keys>
          <Action>Toggle Activation</Action>
        </Hotkey>
        <Hotkey Active="1">
          <Keys><Key>120</Key></Keys>
          <Action>Open URL</Action>
        </Hotkey>
      </Hotkeys>
    </CheatEntry>
    <CheatEntry>
      <ID>6</ID>
      <Description>"Hex float (bit pattern display)"</Description>
      <VariableType>Float</VariableType>
      <ShowAsHex>1</ShowAsHex>
      <Address>HotkeyAnchor+24</Address>
      <Hotkeys>
        <Hotkey Active="1">
          <Keys><Key>121</Key></Keys>
          <Action>Increase Value</Action>
          <Value>1</Value>
        </Hotkey>
      </Hotkeys>
    </CheatEntry>
    <CheatEntry>
      <ID>7</ID>
      <Description>"Four-byte array row"</Description>
      <VariableType>Array of byte</VariableType>
      <ByteLength>4</ByteLength>
      <Address>HotkeyAnchor+28</Address>
      <Hotkeys>
        <Hotkey Active="1">
          <Keys><Key>119</Key></Keys>
          <Action>Increase Value</Action>
          <Value>2</Value>
        </Hotkey>
      </Hotkeys>
    </CheatEntry>
  </CheatEntries>
</CheatTable>
'''


def _binding_lines(engine, record_id):
    return engine.hotkey_registered_keys(record_id)


class RecordHotkeyPlanTests(unittest.TestCase):
    """Plan projection: byte-verifiable metadata for both plan validators."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.ct = root / "hotkeys.ct"
        self.ct.write_text(CT_BODY, encoding="utf-8")
        self.plan = compile_table(self.ct, "FixtureTarget.exe")

    def tearDown(self):
        self.temp.cleanup()

    def _entry(self, identifier):
        return self.plan["entries"][identifier - 1]

    def test_plan_carries_exact_hotkey_metadata(self):
        self.assertEqual(self._entry(1)["hotkeys"], [
            {"keys": [112], "action": "Toggle Activation", "value": "",
             "description": "", "active": True},
            {"keys": [118], "action": "Set Value", "value": "5",
             "description": "", "active": True},
        ])
        self.assertEqual(self._entry(1)["source_hotkey_count"], 2)
        self.assertEqual(self._entry(2)["hotkeys"], [
            {"keys": [113], "action": "Set Value", "value": "999999",
             "description": "Sets the value from the source table", "active": True},
            {"keys": [114], "action": "Increase Value", "value": "3",
             "description": "", "active": True},
            {"keys": [116], "action": "Toggle Activation", "value": "",
             "description": "", "active": True},
            {"keys": [122], "action": "Increase Value", "value": "abc",
             "description": "", "active": True},
            {"keys": [123], "action": "Set Value", "value": "",
             "description": "", "active": True},
        ])
        self.assertEqual(self._entry(2)["source_hotkey_count"], 5)
        # record 5: sorted by raw VK codes; Active=0 stays projected, inactive.
        self.assertEqual(self._entry(5)["hotkeys"], [
            {"keys": [31], "action": "Toggle Activation", "value": "",
             "description": "", "active": True},
            {"keys": [117], "action": "Toggle Activation", "value": "",
             "description": "", "active": False},
            {"keys": [120], "action": "Open URL", "value": "",
             "description": "", "active": True},
        ])
        self.assertEqual(self._entry(5)["source_hotkey_count"], 3)
        self.assertEqual(self._entry(4)["source_hotkey_count"], 1)
        self.assertEqual(self._entry(6)["source_hotkey_count"], 1)
        self.assertEqual(self._entry(7)["source_hotkey_count"], 1)

    def test_compile_warnings_name_every_static_refusal(self):
        self.assertEqual(self.plan["warnings"], [
            "Record 1 ('Hotkey anchor script'): hotkey F7 (Set Value) "
            "not registered: value row is not actionable.",
            "Record 2 ('Hotkey value (4 Bytes)'): hotkey F5 (Toggle Activation) "
            "not registered: record has no activation action.",
            "Record 4 ('Zero-length byte array placeholder'): hotkey F4 (Set Value) "
            "not registered: value row is not actionable.",
            "Record 5 ('Inactive and unmappable hotkeys'): hotkey F9 ('Open URL') "
            "not registered: unsupported action.",
        ])

    def test_plan_hotkey_metadata_is_deterministic(self):
        again = compile_table(self.ct, "FixtureTarget.exe")
        self.assertEqual(json.dumps(self.plan, sort_keys=True,
                                    separators=(",", ":")),
                         json.dumps(again, sort_keys=True,
                                    separators=(",", ":")))

    def _refuse_tampered(self, mutate, message):
        plan = deepcopy(self.plan)
        mutate(plan["entries"][0])
        with self.assertRaisesRegex(NativeRuntimeError, message):
            validate_engine_plan(plan)
        with self.assertRaisesRegex(ValueError, message):
            validate_source_plan(plan)

    def test_tampered_hotkey_metadata_is_rejected_by_both_validators(self):
        self._refuse_tampered(
            lambda e: e["hotkeys"][0].__setitem__("keys", [118, 112]),
            "Hotkey keys must be sorted unique codes up to 255.")
        self._refuse_tampered(
            lambda e: e["hotkeys"][0].__setitem__("keys", [112, 112]),
            "Hotkey keys must be sorted unique codes up to 255.")
        self._refuse_tampered(
            lambda e: e["hotkeys"][0].__setitem__("keys", [256]),
            "Hotkey keys must be sorted unique codes up to 255.")
        self._refuse_tampered(
            lambda e: e["hotkeys"][0].__setitem__("keys", [0]),
            "Hotkey keys must be sorted unique codes up to 255.")
        self._refuse_tampered(
            lambda e: e["hotkeys"][0].__setitem__("keys", "112"),
            "Hotkey keys must be sorted unique codes up to 255.")
        self._refuse_tampered(
            lambda e: e["hotkeys"][0].__setitem__("action", ""),
            "Hotkey action must be bounded nonempty text.")
        self._refuse_tampered(
            lambda e: e["hotkeys"][0].__setitem__("action", "x" * 65),
            "Hotkey action must be bounded nonempty text.")
        self._refuse_tampered(
            lambda e: e["hotkeys"][0].__setitem__("value", "y" * 513),
            "Hotkey value must be bounded text.")
        self._refuse_tampered(
            lambda e: e["hotkeys"][0].__setitem__("description", "z" * 513),
            "Hotkey description must be bounded text.")
        self._refuse_tampered(
            lambda e: e["hotkeys"][0].__setitem__("active", "1"),
            "Hotkey active flag must be a boolean.")
        self._refuse_tampered(
            lambda e: e["hotkeys"][0].__setitem__("extra", 1),
            "Hotkey metadata fields are fixed.")
        self._refuse_tampered(
            lambda e: e["hotkeys"][0].__delitem__("value"),
            "Hotkey metadata fields are fixed.")
        self._refuse_tampered(
            lambda e: e.__setitem__("source_hotkey_count", 0),
            "Hotkey metadata count differs from the source record.")
        self._refuse_tampered(
            lambda e: e.__setitem__("source_hotkey_count", "2"),
            "Hotkey metadata count differs from the source record.")
        self._refuse_tampered(
            lambda e: e["hotkeys"].extend([dict(e["hotkeys"][0])] * 15),
            "Record hotkey metadata must be a bounded list.")
        self._refuse_tampered(
            lambda e: e.__setitem__("hotkeys", "F1"),
            "Record hotkey metadata must be a bounded list.")
        self._refuse_tampered(
            lambda e: e["hotkeys"][0].__setitem__("keys", [112, 112, 112, 112, 112, 112]),
            "Hotkey keys must be sorted unique codes up to 255.")
        self._refuse_tampered(
            lambda e: e.__delitem__("hotkeys"),
            "Hotkey metadata count differs from the source record.")

    def test_hotkeyless_plan_shape_stays_valid_with_zero_count(self):
        # A record without source hotkeys keeps the legacy plan shape
        # (no hotkeys key, source_hotkey_count zero); both validators
        # accept it.  A positive count without its projection is the
        # tamper case above and is refused.
        plan = deepcopy(self.plan)
        entry = plan["entries"][3]
        del entry["hotkeys"]
        entry["source_hotkey_count"] = 0
        validate_source_plan(plan)
        validate_engine_plan(plan)


class RecordHotkeyEngineTests(unittest.TestCase):
    """End-to-end registration, first-wins conflict and value-op dispatch."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        ct = root / "hotkeys.ct"
        ct.write_text(CT_BODY, encoding="utf-8")
        self.plan = compile_table(ct, "FixtureTarget.exe")
        self.memory = Memory()
        self.engine = TrainerEngine(
            self.plan, state_dir=root / "state", process_lock_dir=root / "shared",
            memory_factory=lambda name: self.memory, hook_coordinator=Coordinator())
        self.engine.poll()
        self.assertTrue(self.engine.connected, self.engine.status)

    def tearDown(self):
        if not self.engine.closed:
            self.memory.alive = False
            self.engine.poll()
            self.engine.close()
        self.directory.cleanup()

    def test_no_bindings_before_any_activation(self):
        self.assertEqual(self.engine.hotkey_controller.registrations(), ())
        self.assertEqual(self.engine.hotkey_warnings, [])
        self.assertEqual(self.engine.dispatch_hotkey(HotKeySpec.parse("F1")).status,
                         "unbound")
        self.assertFalse(self.memory.writes)

    def test_activation_registers_hotkeys_in_activation_order(self):
        self.assertTrue(self.engine.toggle(1, True))
        registered = [(item.record_id, item.spec.key)
                      for item in self.engine.hotkey_controller.registrations()]
        # record 1 first (activation order), then the staged value row 2
        # whose provider just went live, then the profile rows 6 and 7 by id.
        self.assertEqual(registered, [(1, "F1"), (2, "F2"), (2, "F3"),
                                      (2, "F11"), (2, "F12"), (6, "F10"),
                                      (7, "F8")])
        self.assertEqual(_binding_lines(self.engine, 1),
                         (("F1", True), ("F7", False)))
        self.assertEqual(_binding_lines(self.engine, 2),
                         (("F2", True), ("F3", True), ("F5", False),
                          ("F11", True), ("F12", True)))
        self.assertEqual(_binding_lines(self.engine, 6), (("F10", True),))
        self.assertEqual(_binding_lines(self.engine, 7), (("F8", True),))
        self.assertEqual(self.engine.hotkey_warnings, [
            "Record 1 ('Hotkey anchor script'): hotkey F7 (Set Value) "
            "not registered: value row is not actionable.",
            "Record 2 ('Hotkey value (4 Bytes)'): hotkey F5 (Toggle Activation) "
            "not registered: record has no activation action.",
        ])

    def test_first_wins_conflict_keeps_loser_functional(self):
        self.assertTrue(self.engine.toggle(1, True))
        self.assertTrue(self.engine.toggle(3, True))
        winner = self.engine.hotkey_controller.find(HotKeySpec.parse("F1"))
        self.assertEqual(winner.record_id, 1)
        self.assertEqual(_binding_lines(self.engine, 3), (("F1", False),))
        self.assertIn(
            "Record 3 ('Conflicting F1 script'): hotkey F1 not registered: "
            "key already bound to record 1 ('Hotkey anchor script') by first-wins",
            self.engine.hotkey_warnings)
        # The losing record keeps its ordinary activation path byte-exact.
        self.assertEqual(self.memory.read(0x1018, 4), b"\x01\x00\x00\x00")
        self.assertFalse(self.engine.toggle(3, False))
        self.assertEqual(self.memory.read(0x1018, 4), b"\x00\x00\x00\x00")
        self.assertFalse(self.engine.toggle(1, False))
        self.assertEqual(self.memory.read(0x1014, 4), b"\x00\x00\x00\x00")
        self.assertEqual(self.engine.hotkey_controller.registrations(), ())

    def test_no_auto_reclaim_until_loser_liveness_changes(self):
        self.assertTrue(self.engine.toggle(1, True))
        self.assertTrue(self.engine.toggle(3, True))
        self.assertEqual(
            self.engine.hotkey_controller.find(HotKeySpec.parse("F1")).record_id, 1)
        # The winner disables: the combination is released, and the losing
        # record does NOT automatically inherit it (named scope limit).
        self.assertFalse(self.engine.toggle(1, False))
        self.assertIsNone(self.engine.hotkey_controller.find(HotKeySpec.parse("F1")))
        self.assertEqual(_binding_lines(self.engine, 3), (("F1", False),))
        self.assertIsNone(self.engine.hotkey_controller.find(HotKeySpec.parse("F1")))
        # The loser re-claims only when its own liveness changes.
        self.assertFalse(self.engine.toggle(3, False))
        self.assertTrue(self.engine.toggle(3, True))
        self.assertEqual(
            self.engine.hotkey_controller.find(HotKeySpec.parse("F1")).record_id, 3)

    def test_staged_value_hotkeys_gate_on_provider_liveness(self):
        self.assertTrue(self.engine.toggle(1, True))
        self.assertIsNotNone(self.engine.hotkey_controller.find(HotKeySpec.parse("F2")))
        # Provider disabled: the staged value row and its hotkeys drop.
        self.assertFalse(self.engine.toggle(1, False))
        self.assertIsNone(self.engine.hotkey_controller.find(HotKeySpec.parse("F2")))
        self.assertIsNone(self.engine.hotkey_controller.find(HotKeySpec.parse("F1")))
        self.assertEqual(self.engine.hotkey_controller.registrations(), ())
        # Provider re-activated: the same bindings re-publish idempotently.
        self.assertTrue(self.engine.toggle(1, True))
        owner = self.engine.hotkey_controller.find(HotKeySpec.parse("F2"))
        self.assertEqual(owner.record_id, 2)
        self.assertIn(self.engine._hotkey_owner, {item.owner for item in
                                                 self.engine.hotkey_controller.registrations()})

    def test_value_dispatch_set_and_step_are_byte_exact(self):
        self.assertTrue(self.engine.toggle(1, True))
        result = self.engine.dispatch_hotkey(HotKeySpec.parse("F2"))
        self.assertEqual(result.status, "triggered")
        self.assertIs(result.outcome.status, ToggleOutcomeStatus.CONFIRMED)
        self.assertFalse(result.outcome.saved)
        self.assertEqual(self.memory.read(0x1010, 4), struct.pack("<I", 999999))
        result = self.engine.dispatch_hotkey(HotKeySpec.parse("F3"))
        self.assertEqual(result.status, "triggered")
        self.assertIs(result.outcome.status, ToggleOutcomeStatus.CONFIRMED)
        self.assertEqual(self.memory.read(0x1010, 4), struct.pack("<I", 1000002))
        # Value operations never persist wishes: record 2 is not a wish row.
        self.assertNotIn(2, self.engine.desired)
        self.assertEqual(
            {address for address, _ in self.memory.writes}, {0x1014, 0x1010})

    def test_value_dispatch_refusals_are_named_and_writeless(self):
        self.assertTrue(self.engine.toggle(1, True))
        writes_before = len(self.memory.writes)
        refusals = [
            (HotKeySpec.parse("F11"), "Hotkey value step must be a decimal integer"),
            (HotKeySpec.parse("F12"), "Enter a whole decimal number"),
            (HotKeySpec.parse("F10"),
             "Hotkey value step is not defined for hex float rows"),
            (HotKeySpec.parse("F8"),
             "Hotkey value step is not defined for byte_array rows"),
        ]
        for spec, detail in refusals:
            result = self.engine.dispatch_hotkey(spec)
            self.assertEqual(result.status, "triggered")
            self.assertIs(result.outcome.status, ToggleOutcomeStatus.FAILED)
            self.assertEqual(result.outcome.detail, detail)
            self.assertFalse(result.tone_played)
        self.assertEqual(len(self.memory.writes), writes_before)
        # Refusals never retire the published binding: the record stays
        # reachable for the same combination on the next press.
        for spec, _ in refusals:
            self.assertIsNotNone(self.engine.hotkey_controller.find(spec))

    def test_activation_dispatch_flips_the_bound_record(self):
        self.assertTrue(self.engine.toggle(1, True))
        self.assertEqual(self.memory.read(0x1014, 4), b"\x01\x00\x00\x00")
        result = self.engine.dispatch_hotkey(HotKeySpec.parse("F1"))
        self.assertEqual(result.status, "triggered")
        self.assertIs(result.outcome.status, ToggleOutcomeStatus.CONFIRMED)
        self.assertTrue(result.outcome.saved)
        self.assertEqual(self.memory.read(0x1014, 4), b"\x00\x00\x00\x00")
        # The disabled record drops every binding (staged dependents too).
        self.assertEqual(self.engine.hotkey_controller.registrations(), ())

    def test_inactive_and_unmappable_hotkeys_are_named(self):
        self.assertTrue(self.engine.toggle(5, True))
        self.assertEqual(self.memory.read(0x1022, 4), b"\x01\x00\x00\x00")
        self.assertEqual(_binding_lines(self.engine, 5),
                         (("VK31", False), ("F6", False), ("F9", False)))
        self.assertIsNone(self.engine.hotkey_controller.find(HotKeySpec.parse("F6")))
        self.assertIsNone(self.engine.hotkey_controller.find(HotKeySpec.parse("F9")))
        self.assertEqual(self.engine.hotkey_warnings, [
            "Record 5 ('Inactive and unmappable hotkeys'): hotkey (Toggle Activation) "
            "not registered: no parsable key.",
            "Record 5 ('Inactive and unmappable hotkeys'): hotkey F9 ('Open URL') "
            "not registered: unsupported action.",
        ])
        # Pressing a combination that was never published is a clean no-op.
        self.assertEqual(
            self.engine.dispatch_hotkey(HotKeySpec.parse("F9")).status, "unbound")

    def test_target_exit_and_close_release_bindings(self):
        self.assertTrue(self.engine.toggle(1, True))
        self.assertTrue(self.engine.toggle(3, True))
        self.assertTrue(self.engine.hotkey_controller.registrations())
        self.memory.alive = False
        self.engine.poll()
        self.assertEqual(self.engine.hotkey_controller.registrations(), ())
        self.assertTrue(self.engine.close())
        self.assertTrue(self.engine.closed)

    def test_dispatch_before_attach_is_suppressed(self):
        # Fresh session, no attach: the focus provider is down, so even a
        # published combination is suppressed before any write or toggle;
        # the OS registration route itself stays an AP-11 gate.
        self.directory.cleanup()
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        ct = root / "hotkeys.ct"
        ct.write_text(CT_BODY, encoding="utf-8")
        plan = compile_table(ct, "FixtureTarget.exe")
        memory = Memory()
        engine = TrainerEngine(
            plan, state_dir=root / "state", process_lock_dir=root / "shared",
            memory_factory=lambda name: memory, hook_coordinator=Coordinator())
        try:
            self.assertIsNone(engine.memory)
            spec = HotKeySpec.parse("F1")
            engine.hotkey_controller.register_first_wins(
                engine._hotkey_owner, 1, spec)
            result = engine.dispatch_hotkey(spec)
            self.assertEqual(result.status, "suppressed-unfocused")
            self.assertIsNone(result.outcome)
            self.assertFalse(memory.writes)
            self.assertEqual(
                engine.dispatch_hotkey(HotKeySpec.parse("F2")).status, "unbound")
        finally:
            engine.close()
            self.directory.cleanup()


class RecordHotkeyDisplayTests(unittest.TestCase):
    """Pure layout contract: original-binding lines and the warning banner."""

    def test_binding_line_renders_original_and_active_state(self):
        self.assertEqual(hotkey_binding_line("F1", True), "F1 (active)")
        self.assertEqual(hotkey_binding_line("F2", False), "F2 (not registered)")
        self.assertEqual(hotkey_binding_line("ctrl+F1", True), "ctrl+F1 (active)")
        with self.assertRaisesRegex(LayoutError, "nonempty key text"):
            hotkey_binding_line("", True)
        with self.assertRaisesRegex(LayoutError, "boolean registration state"):
            hotkey_binding_line("F1", "yes")

    def test_banner_renders_deduped_warnings_with_bounded_tail(self):
        self.assertEqual(hotkey_conflict_banner([]), "")
        self.assertEqual(hotkey_conflict_banner(None), "")
        self.assertEqual(hotkey_conflict_banner(["a"]), "Hotkeys: a")
        self.assertEqual(hotkey_conflict_banner(["a", "b", "c"]), "Hotkeys: a | b | c")
        self.assertEqual(hotkey_conflict_banner(["a", "b", "c", "d"]),
                         "Hotkeys: a | b | c | 1 more")
        self.assertEqual(hotkey_conflict_banner(
                             ["a", "b", "c", "d", "e", "f"], limit=2),
                         "Hotkeys: a | b | 4 more")
        with self.assertRaisesRegex(LayoutError, "positive integer"):
            hotkey_conflict_banner(["a"], limit=0)
        with self.assertRaisesRegex(LayoutError, "warning list"):
            hotkey_conflict_banner("a")
        with self.assertRaisesRegex(LayoutError, "warnings must be text"):
            hotkey_conflict_banner(["a", 1])


if __name__ == "__main__":
    unittest.main()
