"""WP-53 (GC-D7): OS hotkey capture bridge + group-heading hotkeys.

The synthetic CT mirrors the case-29 shape: a plain moHideChildren group
heading (record 61, alt+PRINT) and a flagged moActivateChildrenAsWell
group heading (record 63, alt+HOME) both carry Activate hotkeys next to
an anchor script (record 0) that claims the same alt+PRINT combination.
Post-WP-53 the plain heading toggles its own active state only (CE
parity, no child propagation) and the flagged heading runs the existing
parent-activation cascade over its script child; both bindings register
at attach without any child-liveness gate, and every published binding
is mirrored into the OS bridge.

The bridge is driven through an injected fake seam (never a real window);
the engine is driven through the duck-typed bridge contract and the
pluggable ``hotkey_spec_source`` seam so no test registers a real OS
hotkey.  The real ``RegisterHotKey`` route stays AP-11 evidence.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_native_lua_activation import Memory
from test_native_engine_code import Coordinator
from ct2trainer.native.compiler import compile_table
from ct2trainer.native.engine import (TrainerEngine, NativeRuntimeError,
                                      validate_plan as validate_engine_plan)
from ct2trainer.native.hotkey_bridge import (MOD_ALT, MOD_CONTROL,
                                             HotkeyBridge, HotkeyBridgeError,
                                             HotkeyRegistrationError,
                                             classify_registration_error,
                                             create_hotkey_bridge,
                                             hotkey_bridge_available,
                                             os_key_text, spec_to_os)
from ct2trainer.native.hotkey_model import HotKeySpec


# The AA offsets are hex (CE convention), relative to the scanned anchor
# (Memory base 0x1000): +64 (record 60 patch site -> 0x1064),
# +68 (record 64 patch site -> 0x1068), +72 (value child 62 -> 0x1072),
# +80 (value child 65 -> 0x1080) are all zero-initial in the fixture
# memory.  The record numbering mirrors the case-29 corpus shape
# (60 script, 61/63 group headings, 62/64/65 children).
CT_BODY = '''<?xml version="1.0" encoding="utf-8"?>
<CheatTable CheatEngineTableVersion="45">
  <CheatEntries>
    <CheatEntry>
      <ID>60</ID>
      <Description>"Os anchor script"</Description>
      <VariableType>Auto Assembler Script</VariableType>
      <AssemblerScript>[ENABLE]
aobscanmodule(OsAnchor,FixtureTarget.exe,43 54 32 54 2D 46 49 58 2D 32 30 32 36 2D 30 31)
registersymbol(OsAnchor)
assert(OsAnchor+64,00 00 00 00)
OsAnchor+64:
  dd 1
[DISABLE]
unregistersymbol(OsAnchor)
OsAnchor+64:
  dd 0</AssemblerScript>
      <Hotkeys>
        <Hotkey Active="1">
          <Keys><Key>18</Key><Key>45</Key></Keys>
          <Action>Toggle Activation</Action>
        </Hotkey>
      </Hotkeys>
    </CheatEntry>
    <CheatEntry>
      <ID>61</ID>
      <Description>"[Stats] plain group (moHideChildren only)"</Description>
      <Options moHideChildren="1"/>
      <GroupHeader>1</GroupHeader>
      <Hotkeys>
        <Hotkey Active="1">
          <Keys><Key>18</Key><Key>45</Key></Keys>
          <Action>Activate</Action>
        </Hotkey>
      </Hotkeys>
      <CheatEntries>
        <CheatEntry>
          <ID>62</ID>
          <Description>"stats child value"</Description>
          <VariableType>4 Bytes</VariableType>
          <Address>OsAnchor+72</Address>
        </CheatEntry>
      </CheatEntries>
    </CheatEntry>
    <CheatEntry>
      <ID>63</ID>
      <Description>"[Battle] flagged group (moActivateChildrenAsWell)"</Description>
      <Options moActivateChildrenAsWell="1"/>
      <GroupHeader>1</GroupHeader>
      <Hotkeys>
        <Hotkey Active="1">
          <Keys><Key>18</Key><Key>36</Key></Keys>
          <Action>Activate</Action>
        </Hotkey>
      </Hotkeys>
      <CheatEntries>
        <CheatEntry>
          <ID>64</ID>
          <Description>"battle child script"</Description>
          <VariableType>Auto Assembler Script</VariableType>
          <AssemblerScript>[ENABLE]
aobscanmodule(OsAnchor2,FixtureTarget.exe,43 54 32 54 2D 46 49 58 2D 32 30 32 36 2D 30 31)
registersymbol(OsAnchor2)
assert(OsAnchor2+68,00 00 00 00)
OsAnchor2+68:
  dd 1
[DISABLE]
unregistersymbol(OsAnchor2)
OsAnchor2+68:
  dd 0</AssemblerScript>
        </CheatEntry>
        <CheatEntry>
          <ID>65</ID>
          <Description>"battle child value"</Description>
          <VariableType>4 Bytes</VariableType>
          <Address>OsAnchor+80</Address>
        </CheatEntry>
      </CheatEntries>
    </CheatEntry>
  </CheatEntries>
</CheatTable>
'''

ALT_PRINT = HotKeySpec.parse("alt+PRINT")
ALT_HOME = HotKeySpec.parse("alt+HOME")
CTRL_ALT_F1 = HotKeySpec.parse("ctrl+alt+F1")
NOREPEAT = 0x4000


class FakeSeam:
    """Scripted stand-in for the Windows win32 seam surface."""

    def __init__(self, fail_codes=None, handle=4242):
        self.fail_codes = dict(fail_codes or {})
        self.handle = handle
        self.handler = None
        self.registered = {}
        self.unregistered = []
        self.last_error_value = 0
        self.destroyed = False

    def connect(self, handler):
        self.handler = handler
        return self.handle

    def register_hotkey(self, hotkey_id, mods, vk):
        key = (mods, vk)
        if key in self.fail_codes:
            self.last_error_value = self.fail_codes[key]
            return False
        self.registered[hotkey_id] = key
        return True

    def unregister_hotkey(self, hotkey_id):
        self.unregistered.append(hotkey_id)
        return self.registered.pop(hotkey_id, None) is not None

    def last_error(self):
        return self.last_error_value

    def destroy(self):
        self.destroyed = True


class FakeBridge:
    """Engine-side duck type: the exact contract the engine drives
    (register/unregister/take_specs/close) with scripted per-spec
    failures and an injectable captured-spec queue."""

    def __init__(self, fail_specs=()):
        self.fail_specs = set(fail_specs)
        self.registered = set()
        self.released = []
        self.queued = []
        self.destroyed = False

    def register(self, spec):
        if spec in self.fail_specs:
            raise HotkeyRegistrationError(
                os_key_text(spec),
                "the combination is already registered by another "
                "process (E_ACCESS_DENIED)")
        self.registered.add(spec)
        return len(self.registered)

    def unregister(self, spec):
        self.registered.discard(spec)
        self.released.append(spec)
        return True

    def push(self, spec):
        self.queued.append(spec)

    def take_specs(self):
        specs, self.queued = self.queued, []
        return tuple(specs)

    def close(self):
        self.destroyed = True
        self.registered.clear()


class OsHotkeySpecHelpersTests(unittest.TestCase):
    """Pure bridge helpers: canonical mapping and named refusals."""

    def test_spec_to_os_folds_modifiers_and_main_key(self):
        self.assertEqual(spec_to_os(CTRL_ALT_F1), (MOD_CONTROL | MOD_ALT, 112))
        self.assertEqual(spec_to_os(ALT_PRINT), (MOD_ALT, 45))
        self.assertEqual(spec_to_os(ALT_HOME), (MOD_ALT, 36))

    def test_os_key_text_is_canonical_sorted(self):
        self.assertEqual(os_key_text(CTRL_ALT_F1), "alt+ctrl+F1")
        self.assertEqual(os_key_text(ALT_PRINT), "alt+PRINT")
        self.assertEqual(os_key_text(ALT_HOME), "alt+HOME")

    def test_refuses_non_spec_values(self):
        for bad in ("alt+PRINT", None, 45):
            with self.assertRaises(HotkeyBridgeError):
                spec_to_os(bad)
            with self.assertRaises(HotkeyBridgeError):
                os_key_text(bad)

    def test_refuses_main_key_outside_the_bounded_vk_table(self):
        # 16-char tokens are admissible hotkey text; the bounded VK table
        # still refuses them at registration time, named.
        spec = HotKeySpec.parse("ABCDEFGHIJKLMNOP")
        with self.assertRaisesRegex(HotkeyBridgeError,
                                    "no virtual key for the OS bridge"):
            spec_to_os(spec)

    def test_classify_registration_error_named_classes(self):
        self.assertEqual(
            classify_registration_error(5),
            "the combination is already registered by another "
            "process (E_ACCESS_DENIED)")
        self.assertEqual(
            classify_registration_error(87),
            "the key combination is invalid for RegisterHotKey "
            "(E_INVALID_PARAMETER)")
        self.assertEqual(
            classify_registration_error(1234),
            "RegisterHotKey failed with Win32 error 1234")

    def test_classify_registration_error_refuses_invalid_codes(self):
        for bad in (0, -1, "5", None):
            with self.assertRaises(HotkeyBridgeError):
                classify_registration_error(bad)

    def test_availability_and_factory_are_platform_gated(self):
        self.assertEqual(hotkey_bridge_available(), sys.platform == "win32")
        with patch.object(sys, "platform", "linux"):
            self.assertFalse(hotkey_bridge_available())
            self.assertIsNone(create_hotkey_bridge())
            with self.assertRaisesRegex(HotkeyBridgeError, "Windows-only"):
                HotkeyBridge()


class OsHotkeyBridgeSeamTests(unittest.TestCase):
    """The tested HotkeyBridge over an injected seam: IDs, failures, close."""

    def _bridge(self, fail_codes=None):
        seam = FakeSeam(fail_codes)
        return HotkeyBridge(seam=seam), seam

    def test_window_handle_contract(self):
        with self.assertRaisesRegex(HotkeyBridgeError,
                                    "window handle is invalid"):
            HotkeyBridge(seam=FakeSeam(handle=0))

    def test_id_maps_to_spec_and_take_specs_drains(self):
        bridge, seam = self._bridge()
        self.assertEqual(bridge.register(ALT_PRINT), 1)
        self.assertEqual(bridge.register(ALT_HOME), 2)
        self.assertEqual(bridge.take_specs(), ())
        seam.handler(1)  # WM_HOTKEY for alt+PRINT
        seam.handler(2)  # WM_HOTKEY for alt+HOME
        self.assertEqual(bridge.take_specs(), (ALT_PRINT, ALT_HOME))
        self.assertEqual(bridge.take_specs(), ())

    def test_register_is_idempotent_per_combination(self):
        bridge, seam = self._bridge()
        first = bridge.register(ALT_PRINT)
        again = bridge.register(ALT_PRINT)
        self.assertEqual(first, again)
        self.assertEqual(len(seam.registered), 1)
        # MOD_NOREPEAT is OR'ed into every OS registration.
        self.assertEqual(seam.registered[first], (MOD_ALT | NOREPEAT, 45))

    def test_registration_failure_is_named_byte_exact(self):
        bridge, seam = self._bridge({(MOD_ALT | NOREPEAT, 45): 5})
        with self.assertRaises(HotkeyRegistrationError) as caught:
            bridge.register(ALT_PRINT)
        self.assertEqual(
            str(caught.exception),
            "OS hotkey registration failed for alt+PRINT: the combination "
            "is already registered by another process (E_ACCESS_DENIED).")
        self.assertFalse(bridge.is_registered(ALT_PRINT))
        self.assertEqual(seam.registered, {})

    def test_late_event_for_released_id_is_dropped(self):
        bridge, seam = self._bridge()
        hotkey_id = bridge.register(ALT_PRINT)
        self.assertTrue(bridge.unregister(ALT_PRINT))
        seam.handler(hotkey_id)  # late WM_HOTKEY just after the release
        self.assertEqual(bridge.take_specs(), ())

    def test_close_releases_everything_and_blocks_re_register(self):
        bridge, seam = self._bridge()
        bridge.register(ALT_PRINT)
        bridge.register(ALT_HOME)
        bridge.close()
        self.assertEqual(len(seam.unregistered), 2)
        self.assertTrue(seam.destroyed)
        with self.assertRaisesRegex(HotkeyBridgeError,
                                    "hotkey bridge is closed"):
            bridge.register(ALT_PRINT)
        # close is idempotent; unregister after close is a clean False.
        bridge.close()
        self.assertFalse(bridge.unregister(ALT_HOME))

    def test_unregister_requires_a_canonical_spec(self):
        bridge, _ = self._bridge()
        with self.assertRaises(HotkeyBridgeError):
            bridge.unregister("alt+PRINT")


class OsHotkeyEngineTests(unittest.TestCase):
    """case-29-shape fixture: heading hotkeys, OS mirror and the poll drain."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        ct = root / "os_hotkeys.ct"
        ct.write_text(CT_BODY, encoding="utf-8")
        self.root = root
        self.plan = compile_table(ct, "FixtureTarget.exe")
        self.memory = Memory()
        self.engine = self._make_engine()
        # No poll yet: tests attach the OS bridge (if any) before the first
        # tick, mirroring the trainer UI ordering (bridge at start, attach
        # on the first poll).

    def _make_engine(self):
        return TrainerEngine(
            self.plan, state_dir=self.root / "state",
            process_lock_dir=self.root / "shared",
            memory_factory=lambda name: self.memory,
            hook_coordinator=Coordinator())

    def _connect(self):
        self.engine.poll()
        self.assertTrue(self.engine.connected, self.engine.status)
        return self.engine

    def tearDown(self):
        if not self.engine.closed:
            self.memory.alive = False
            self.engine.poll()
            self.engine.close()
        self.directory.cleanup()

    def test_plan_shape_headings_carry_hotkeys_without_compile_warning(self):
        plan = self.plan
        self.assertEqual(plan["warnings"], [])
        by_id = {entry["id"]: entry for entry in plan["entries"]}
        self.assertEqual(by_id[60]["kind"], "script")
        self.assertEqual(by_id[61]["kind"], "heading")
        self.assertTrue(by_id[61]["supported"])
        self.assertNotIn("parent_activation", by_id[61])
        self.assertEqual(by_id[61]["hotkeys"], [
            {"keys": [18, 45], "action": "Activate", "value": "",
             "description": "", "active": True}])
        self.assertEqual(by_id[63]["kind"], "heading")
        self.assertEqual(by_id[63]["parent_activation"], "direct_activation")
        self.assertEqual(by_id[63]["hotkeys"], [
            {"keys": [18, 36], "action": "Activate", "value": "",
             "description": "", "active": True}])
        self.assertEqual(by_id[62]["kind"], "value")
        self.assertEqual(by_id[65]["kind"], "value")
        self.assertEqual(by_id[64]["kind"], "script")
        self.assertEqual(plan["parent_relations"],
                         {"63": {"64": "direct_activation",
                                 "65": "direct_activation"}})
        validate_engine_plan(plan)

    def test_headings_register_at_attach_without_child_liveness(self):
        self._connect()
        controller = self.engine.hotkey_controller
        # Neither heading's child is live yet; both bindings are up anyway
        # (CE registers group hotkeys at table load).
        self.assertEqual(controller.find(ALT_PRINT).record_id, 61)
        self.assertEqual(controller.find(ALT_HOME).record_id, 63)
        self.assertEqual(self.engine.hotkey_warnings, [])
        self.assertEqual(self.engine.applied, {})
        self.assertFalse(self.memory.writes)
        self.assertEqual(self.engine.hotkey_registered_keys(61),
                         (("alt+PRINT", True),))
        self.assertEqual(self.engine.hotkey_registered_keys(63),
                         (("alt+HOME", True),))

    def test_plain_heading_dispatch_toggles_own_state_only(self):
        self._connect()
        result = self.engine.dispatch_hotkey(ALT_PRINT)
        self.assertEqual(result.status, "triggered")
        self.assertEqual(result.record_id, 61)
        # Own active state only: applied with an empty effect list, the
        # wish persisted, no target-memory operation at all.
        self.assertIn(61, self.engine.applied)
        self.assertEqual(self.engine.applied[61], [])
        self.assertEqual(self.engine.desired, {61})
        self.assertFalse(self.memory.writes)
        # No child propagation: the value child keeps its original bytes.
        self.assertEqual(self.memory.read(0x1072, 4), b"\x00\x00\x00\x00")
        # Directionless second press flips the heading back off.
        result = self.engine.dispatch_hotkey(ALT_PRINT)
        self.assertEqual(result.status, "triggered")
        self.assertEqual(self.engine.applied, {})
        self.assertEqual(self.engine.desired, set())

    def test_flagged_heading_dispatch_runs_the_cascade(self):
        self._connect()
        # direct_activation semantics: the script child's own wish is set
        # through its ordinary toggle first (the existing cascade contract).
        self.assertTrue(self.engine.toggle(64, True))
        self.assertEqual(self.memory.read(0x1068, 4), b"\x01\x00\x00\x00")
        # The flagged group ON via its hotkey: the wished child stays on,
        # the value child is skipped (no effect of its own) and the anchor
        # script (record 60) stays untouched.
        result = self.engine.dispatch_hotkey(ALT_HOME)
        self.assertEqual(result.status, "triggered")
        self.assertEqual(result.record_id, 63)
        self.assertIn(64, self.engine.applied)
        self.assertNotIn(63, self.engine.applied)
        self.assertNotIn(60, self.engine.applied)
        self.assertEqual(self.memory.read(0x1068, 4), b"\x01\x00\x00\x00")
        self.assertEqual(self.memory.read(0x1064, 4), b"\x00\x00\x00\x00")
        self.assertEqual(self.memory.read(0x1072, 4), b"\x00\x00\x00\x00")
        self.assertEqual(self.memory.read(0x1080, 4), b"\x00\x00\x00\x00")
        # Save boundary: the child keeps its own wish; the heading wish is
        # saved at the parent-activation save boundary.
        self.assertEqual(self.engine.desired, {63, 64})
        # Directionless second press runs the OFF cascade: the explicitly
        # active child is restored bottom-up and both wishes are cleared.
        result = self.engine.dispatch_hotkey(ALT_HOME)
        self.assertEqual(result.status, "triggered")
        self.assertNotIn(64, self.engine.applied)
        self.assertEqual(self.memory.read(0x1068, 4), b"\x00\x00\x00\x00")
        self.assertEqual(self.engine.desired, set())

    def test_os_failure_warning_and_programmatic_dispatch_survive(self):
        bridge = FakeBridge(fail_specs={ALT_PRINT})
        self.engine.hotkey_bridge = bridge
        self._connect()  # the attach-time mirror hits the failing spec
        self.assertEqual(
            self.engine.hotkey_warnings,
            ["OS hotkey registration failed for alt+PRINT: the combination "
             "is already registered by another process (E_ACCESS_DENIED)."])
        self.assertEqual(bridge.registered, {ALT_HOME})
        # The binding stays published for the programmatic dispatch path.
        self.assertEqual(self.engine.hotkey_controller.find(ALT_PRINT).record_id, 61)
        result = self.engine.dispatch_hotkey(ALT_PRINT)
        self.assertEqual(result.status, "triggered")
        self.assertIn(61, self.engine.applied)
        # Target exit releases only the registration that succeeded.
        self.memory.alive = False
        self.engine.poll()
        self.assertEqual(bridge.released, [ALT_HOME])

    def test_poll_drain_via_spec_source_and_bridge_queue(self):
        bridge = FakeBridge()
        self.engine.hotkey_bridge = bridge
        self._connect()  # the attach-time mirror lands both bindings
        self.assertEqual(bridge.registered, {ALT_PRINT, ALT_HOME})
        # The pluggable spec source takes precedence over the bridge queue.
        drained = []

        def source():
            if not drained:
                drained.append(True)
                return (ALT_PRINT,)
            return ()

        self.engine.hotkey_spec_source = source
        bridge.push(ALT_HOME)
        self.engine.poll()
        # The source owns the drain while set: the plain heading toggles,
        # and the queued bridge spec stays queued for a later tick.
        self.assertIn(61, self.engine.applied)
        self.assertEqual(self.engine.applied[61], [])
        self.assertEqual(bridge.queued, [ALT_HOME])
        # Once the source is cleared, the bridge queue resumes the drain and
        # delivers its queued combination through the same dispatch path
        # (the flagged group's direct-activation ON; no child wish is set,
        # so nothing is pulled in and only the heading wish is saved).
        self.engine.hotkey_spec_source = None
        self.engine.poll()
        self.assertEqual(bridge.queued, [])
        self.assertEqual(self.engine.applied, {61: []})
        self.assertEqual(self.memory.read(0x1068, 4), b"\x00\x00\x00\x00")
        self.assertEqual(self.engine.desired, {61, 63})

    def test_drain_refuses_non_spec_items(self):
        self.engine.hotkey_spec_source = lambda: ("bogus",)
        with self.assertRaisesRegex(
                NativeRuntimeError,
                "Hotkey spec source yielded a non-HotKeySpec item."):
            self.engine._hotkey_drain()

    def test_first_wins_group_vs_record_conflict(self):
        self._connect()
        # Fresh attach: the heading claims alt+PRINT before the (not yet
        # live) script record does.
        self.assertEqual(
            self.engine.hotkey_controller.find(ALT_PRINT).record_id, 61)
        self.assertTrue(self.engine.toggle(60, True))
        self.assertIn(
            "Record 60 ('Os anchor script'): hotkey alt+PRINT not registered: "
            "key already bound to record 61 "
            "('[Stats] plain group (moHideChildren only)') by first-wins",
            self.engine.hotkey_warnings)
        # The heading keeps the binding; dispatch still targets it, and the
        # losing record stays fully functional through its own path.
        self.assertEqual(
            self.engine.hotkey_controller.find(ALT_PRINT).record_id, 61)
        result = self.engine.dispatch_hotkey(ALT_PRINT)
        self.assertEqual(result.status, "triggered")
        self.assertEqual(result.record_id, 61)
        self.assertIn(61, self.engine.applied)
        self.assertEqual(self.memory.read(0x1064, 4), b"\x01\x00\x00\x00")

    def test_plain_heading_wish_replay_on_reattach(self):
        self._connect()
        self.engine.dispatch_hotkey(ALT_PRINT)
        self.assertIn(61, self.engine.applied)
        self.assertEqual(self.engine.desired, {61})
        # Confirmed target exit drops the effect but keeps the saved wish.
        self.memory.alive = False
        self.engine.poll()
        self.assertEqual(self.engine.desired, {61})
        self.engine.close()
        self.assertTrue(self.engine.closed)
        # A fresh engine over the same state dir restores the heading state.
        self.memory = Memory()
        self.engine = self._make_engine()
        self.engine.poll()
        self.assertTrue(self.engine.connected, self.engine.status)
        self.assertIn(61, self.engine.applied)
        self.assertEqual(self.engine.applied[61], [])
        self.assertEqual(self.engine.desired, {61})
        self.assertEqual(
            self.engine.hotkey_controller.find(ALT_PRINT).record_id, 61)
        # And the restored heading toggles back off through its hotkey.
        result = self.engine.dispatch_hotkey(ALT_PRINT)
        self.assertEqual(result.status, "triggered")
        self.assertEqual(self.engine.applied, {})
        self.assertEqual(self.engine.desired, set())

    def test_dispatch_before_attach_is_unbound(self):
        # No binding is published before the attach tick.
        result = self.engine.dispatch_hotkey(ALT_PRINT)
        self.assertEqual(result.status, "unbound")
        self.assertEqual(self.engine.hotkey_controller.registrations(), ())
        # After attach, the plain heading owns the combination.
        self._connect()
        self.assertEqual(self.engine.hotkey_controller.find(ALT_PRINT).record_id, 61)

    def test_close_destroys_the_bridge_and_releases_everything(self):
        bridge = FakeBridge()
        self.engine.hotkey_bridge = bridge
        self._connect()
        self.assertEqual(bridge.registered, {ALT_PRINT, ALT_HOME})
        self.memory.alive = False
        self.engine.poll()  # confirmed target exit releases both specs
        self.assertEqual(set(bridge.released), {ALT_PRINT, ALT_HOME})
        self.assertTrue(self.engine.close())
        self.assertTrue(bridge.destroyed)
        self.assertEqual(bridge.registered, set())
        self.assertIsNone(self.engine.hotkey_bridge)


if __name__ == "__main__":
    unittest.main()
