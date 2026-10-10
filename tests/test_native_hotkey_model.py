"""Hotkey/rebind model: owner-bound registration, protected toggle path, tone policy."""
from __future__ import annotations

import unittest

from ct2trainer.native.hotkey_model import (
    HotkeyCollisionError,
    HotkeyController,
    HotkeyModelError,
    HotKeySpec,
    ToggleOutcome,
    ToggleOutcomeStatus,
)


class FakeGate:
    """Stands in for the protected engine toggle path (TrainerEngine.toggle)."""

    def __init__(self, outcome=None, blocked=False):
        self.outcome = outcome or ToggleOutcome(ToggleOutcomeStatus.CONFIRMED, True)
        self.blocked = blocked
        self.calls = []

    def toggle(self, identifier):
        self.calls.append(identifier)
        return self.outcome


def _focused(**flags):
    return {
        "focused": flags.get("focused", True),
        "text_focus": flags.get("text_focus", False),
    }


def _controller(state, gate=None, tones=None):
    return HotkeyController(
        gate or FakeGate(),
        focus_provider=lambda: state["focused"],
        text_focus_provider=lambda: state["text_focus"],
        tone_recorder=lambda record, status: tones.append((record, status)) if tones is not None else None,
    )


class HotkeyRegistrationTests(unittest.TestCase):
    def test_register_and_dispatch_runs_the_protected_toggle_path(self):
        state = _focused()
        gate = FakeGate()
        tones = []
        controller = _controller(state, gate=gate, tones=tones)
        spec = HotKeySpec.parse("Ctrl+F1")
        controller.register("trainer-1", 7, spec)
        result = controller.dispatch(spec)
        self.assertEqual(result.status, "triggered")
        self.assertEqual(gate.calls, [7])
        self.assertEqual(tones, [(7, "confirmed")])
        self.assertEqual(controller.owner_of(7), "trainer-1")

    def test_same_record_rebind_replaces_the_binding(self):
        state = _focused()
        gate = FakeGate()
        controller = _controller(state, gate=gate)
        old = HotKeySpec.parse("Ctrl+F1")
        new = HotKeySpec.parse("Alt+F2")
        controller.register("trainer-1", 7, old)
        self.assertTrue(controller.unregister("trainer-1", 7))
        controller.register("trainer-1", 7, new)
        self.assertEqual(controller.dispatch(old).status, "unbound")
        self.assertEqual(controller.dispatch(new).status, "triggered")
        self.assertEqual(gate.calls, [7])

    def test_collision_between_two_records_is_rejected_with_owner(self):
        state = _focused()
        controller = _controller(state)
        spec = HotKeySpec.parse("Ctrl+Alt+F3")
        controller.register("trainer-1", 5, spec)
        with self.assertRaises(HotkeyCollisionError) as ctx:
            controller.register("trainer-2", 6, spec)
        self.assertEqual(ctx.exception.existing_record_id, 5)
        self.assertEqual(ctx.exception.requested_record_id, 6)
        # the original binding is untouched and still the only dispatch target
        self.assertEqual([item.record_id for item in controller.registrations()], [5])
        self.assertEqual(controller.dispatch(spec).record_id, 5)

    def test_collision_is_order_independent_on_modifiers(self):
        state = _focused()
        controller = _controller(state)
        controller.register("trainer-1", 5, HotKeySpec.parse("Ctrl+Alt+F9"))
        with self.assertRaises(HotkeyCollisionError):
            controller.register("trainer-2", 6, HotKeySpec.parse("Alt+Ctrl+F9"))
        # equal specs collapse to one canonical form
        self.assertEqual(HotKeySpec.parse("Ctrl+Alt+F9"), HotKeySpec.parse("Alt+Ctrl+F9"))

    def test_owner_binding_blocks_foreign_unregister_and_rebind(self):
        state = _focused()
        controller = _controller(state)
        controller.register("trainer-1", 5, HotKeySpec.parse("F1"))
        self.assertFalse(controller.unregister("trainer-2", 5))
        self.assertEqual([item.owner for item in controller.registrations()], ["trainer-1"])
        with self.assertRaises(HotkeyModelError):
            controller.register("trainer-2", 5, HotKeySpec.parse("F2"))

    def test_record_cannot_have_two_published_bindings(self):
        state = _focused()
        controller = _controller(state)
        controller.register("trainer-1", 5, HotKeySpec.parse("F1"))
        with self.assertRaises(HotkeyModelError):
            controller.register("trainer-1", 5, HotKeySpec.parse("F2"))

    def test_cancel_pending_registration_before_publication(self):
        state = _focused()
        controller = _controller(state)
        spec = HotKeySpec.parse("Ctrl+F5")
        controller.register("trainer-1", 5, spec, commit=False)
        self.assertEqual(len(controller.pending()), 1)
        self.assertEqual(controller.registrations(), ())
        self.assertTrue(controller.cancel_pending("trainer-1", 5))
        self.assertFalse(controller.cancel_pending("trainer-1", 5))
        self.assertEqual(controller.registrations(), ())
        self.assertEqual(controller.dispatch(spec).status, "unbound")

    def test_commit_pending_rechecks_collision_against_new_bindings(self):
        state = _focused()
        controller = _controller(state)
        spec = HotKeySpec.parse("Ctrl+F5")
        controller.register("trainer-1", 5, spec, commit=False)
        controller.register("trainer-2", 6, spec)  # claims the key first
        with self.assertRaises(HotkeyCollisionError):
            controller.commit_pending("trainer-1", 5)
        self.assertEqual(controller.dispatch(spec).record_id, 6)

    def test_close_cleans_up_exactly_the_owners_entries(self):
        state = _focused()
        controller = _controller(state)
        controller.register("trainer-1", 5, HotKeySpec.parse("F1"))
        controller.register("trainer-1", 6, HotKeySpec.parse("F2"), commit=False)
        controller.register("trainer-2", 7, HotKeySpec.parse("F3"))
        published, pending = controller.close("trainer-1")
        self.assertEqual((published, pending), (1, 1))
        self.assertEqual([item.record_id for item in controller.registrations()], [7])
        self.assertEqual([item.record_id for item in controller.pending()], [])


class HotkeyDispatchGateTests(unittest.TestCase):
    def test_dispatch_is_suppressed_when_the_target_is_not_focused(self):
        state = _focused(focused=False)
        gate = FakeGate()
        controller = _controller(state, gate=gate)
        spec = HotKeySpec.parse("Ctrl+F1")
        controller.register("trainer-1", 5, spec)
        result = controller.dispatch(spec)
        self.assertEqual(result.status, "suppressed-unfocused")
        self.assertEqual(gate.calls, [])
        self.assertIsNone(result.outcome)

    def test_dispatch_is_suppressed_while_a_text_field_has_focus(self):
        state = _focused(text_focus=True)
        gate = FakeGate()
        controller = _controller(state, gate=gate)
        spec = HotKeySpec.parse("P")
        controller.register("trainer-1", 5, spec)
        result = controller.dispatch(spec)
        self.assertEqual(result.status, "suppressed-text-focus")
        self.assertEqual(gate.calls, [])

    def test_dispatch_is_suppressed_when_the_controller_is_blocked(self):
        state = _focused()
        gate = FakeGate(blocked=True)
        controller = _controller(state, gate=gate)
        spec = HotKeySpec.parse("Ctrl+F1")
        controller.register("trainer-1", 5, spec)
        result = controller.dispatch(spec)
        self.assertEqual(result.status, "suppressed-blocked")
        self.assertEqual(gate.calls, [])

    def test_unbound_combination_never_reaches_the_gate(self):
        state = _focused()
        gate = FakeGate()
        controller = _controller(state, gate=gate)
        result = controller.dispatch(HotKeySpec.parse("Ctrl+F9"))
        self.assertEqual(result.status, "unbound")
        self.assertEqual(gate.calls, [])


class HotkeyTonePolicyTests(unittest.TestCase):
    def _dispatch_with(self, outcome):
        tones = []
        gate = FakeGate(outcome=outcome)
        state = _focused()
        controller = _controller(state, gate=gate, tones=tones)
        spec = HotKeySpec.parse("Ctrl+F1")
        controller.register("trainer-1", 5, spec)
        return controller.dispatch(spec), tones

    def test_confirmed_saved_toggle_plays_the_tone_exactly_once(self):
        result, tones = self._dispatch_with(ToggleOutcome(ToggleOutcomeStatus.CONFIRMED, True))
        self.assertEqual(result.status, "triggered")
        self.assertEqual(tones, [(5, "confirmed")])

    def test_pending_outcome_is_silent(self):
        result, tones = self._dispatch_with(ToggleOutcome(ToggleOutcomeStatus.PENDING, False))
        self.assertEqual(result.status, "triggered")
        self.assertEqual(tones, [])

    def test_failed_outcome_is_silent(self):
        result, tones = self._dispatch_with(ToggleOutcome(ToggleOutcomeStatus.FAILED, False))
        self.assertEqual(result.status, "triggered")
        self.assertEqual(tones, [])

    def test_unknown_outcome_is_silent(self):
        result, tones = self._dispatch_with(ToggleOutcome(ToggleOutcomeStatus.UNKNOWN, False))
        self.assertEqual(result.status, "triggered")
        self.assertEqual(tones, [])

    def test_confirmed_without_state_save_is_silent(self):
        result, tones = self._dispatch_with(ToggleOutcome(ToggleOutcomeStatus.CONFIRMED, False))
        self.assertEqual(result.status, "triggered")
        self.assertEqual(tones, [])


class HotKeySpecValidationTests(unittest.TestCase):
    def test_parse_canonicalizes_key_and_modifiers(self):
        spec = HotKeySpec.parse("ctrl+f1")
        self.assertEqual(spec.key, "F1")
        self.assertEqual(spec.modifiers, frozenset({"ctrl"}))
        self.assertEqual(spec.as_list(), ["ctrl", "F1"])

    def test_modifiers_only_are_rejected(self):
        with self.assertRaises(HotkeyModelError):
            HotKeySpec.parse("Ctrl+Alt")

    def test_two_main_keys_are_rejected(self):
        with self.assertRaises(HotkeyModelError):
            HotKeySpec.parse("Ctrl+F1+F2")

    def test_empty_parts_are_rejected(self):
        with self.assertRaises(HotkeyModelError):
            HotKeySpec.parse("Ctrl++F1")
        with self.assertRaises(HotkeyModelError):
            HotKeySpec.parse("")

    def test_unknown_modifier_is_rejected(self):
        with self.assertRaises(HotkeyModelError):
            HotKeySpec.parse("Win+F1")

    def test_modifier_as_main_key_is_rejected(self):
        with self.assertRaises(HotkeyModelError):
            HotKeySpec(key="ctrl")

    def test_controller_requires_a_protected_gate_and_providers(self):
        with self.assertRaises(HotkeyModelError):
            HotkeyController(None, focus_provider=lambda: True, text_focus_provider=lambda: False)
        with self.assertRaises(HotkeyModelError):
            HotkeyController(FakeGate(), focus_provider=None, text_focus_provider=lambda: False)

    def test_register_validates_owner_and_record_id(self):
        state = _focused()
        controller = _controller(state)
        for bad_owner in ("", "x" * 257):
            with self.assertRaises(HotkeyModelError):
                controller.register(bad_owner, 5, HotKeySpec.parse("F1"))
        for bad_record in (0, -1, "5"):
            with self.assertRaises(HotkeyModelError):
                controller.register("trainer-1", bad_record, HotKeySpec.parse("F1"))


if __name__ == "__main__":
    unittest.main()
