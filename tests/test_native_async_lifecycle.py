"""Compiler acceptance tests for async (CT Async="1") script records.

Slice A of the AP-07-2 async lifecycle wiring (plan section 8): the
compiler no longer refuses records marked Async="1". Each such record
keeps its regular profile (byte patch, program, one-shot, or Lua
program) and receives a plan-level ``async`` marker that the engine
will use for the async activation lifecycle. The marker is attached
only to entries that are still supported after dependency analysis,
and both plan validators reject malformed markers fail-closed.
Engine-side pending/confirm/drain semantics are the next slice.
"""
import json
import tempfile
import unittest
from pathlib import Path
import xml.sax.saxutils

from ct2trainer.native.compiler import NativeCompileError, compile_table, validate_plan
from ct2trainer.native.engine import validate_plan as validate_runtime_plan


def script_record(entry_id, script, label="Option", attributes=""):
    return (f'<CheatEntry><ID>{entry_id}</ID><Description>{label}</Description>'
            '<VariableType>Auto Assembler Script</VariableType>'
            f'<AssemblerScript {attributes}>{xml.sax.saxutils.escape(script)}</AssemblerScript></CheatEntry>')


def value_record(entry_id, address="1000", value_type="4 Bytes"):
    return (f'<CheatEntry><ID>{entry_id}</ID><Description>Value {entry_id}</Description>'
            f'<VariableType>{value_type}</VariableType><Address>{address}</Address></CheatEntry>')


PATCH_SCRIPT = ("[ENABLE]\nassert(Target.exe+10,00)\nTarget.exe+10:\ndb 01\n"
                "[DISABLE]\nassert(Target.exe+10,01)\nTarget.exe+10:\ndb 00")
PROGRAM_SCRIPT = ("[ENABLE]\naobscanmodule(Anchor,Target.exe,54 46)\n"
                  "registersymbol(Anchor)\nalloc(data,100,Anchor)\ndata:\ndq 0\n"
                  "registersymbol(data)\n[DISABLE]\nunregistersymbol(data)\ndealloc(data)")
LUA_SCRIPT = "[ENABLE]\n{$lua}\nreturn nil\n{$asm}\n[DISABLE]"
LOCATOR_SCRIPT = ("[ENABLE]\naobscanmodule(Anchor,Target.exe,54 46)\n"
                  "registersymbol(Anchor)\n[DISABLE]\nunregistersymbol(Anchor)")
CONSUMER_SCRIPT = ("[ENABLE]\nassert(Anchor,00)\nAnchor+1:\ndb 01\n"
                   "[DISABLE]\nassert(Anchor,00)\nAnchor+1:\ndb 00")
# WP-29: an ENABLE that carries only alloc/registersymbol is now a supported
# allocation-only init profile, so the canonical blocked fixture is the
# genuinely empty ENABLE.
BLOCKED_SCRIPT = "[ENABLE]\n[DISABLE]\n"
ONESHOT_SCRIPT = "[ENABLE]\nassert(Target.exe+10,00)\nTarget.exe+10:\ndb 01"


class _AsyncCompilerBase(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.table_path = Path(self.directory.name) / "async.CT"

    def compile(self, body, selected_ids=None):
        self.table_path.write_text(
            '<CheatTable CheatEngineTableVersion="52"><CheatEntries>' + body
            + '</CheatEntries></CheatTable>', encoding="utf-8")
        return compile_table(self.table_path, "Target.exe", selected_ids=selected_ids)

    def entry(self, plan, entry_id=0):
        return next(entry for entry in plan["entries"] if entry["id"] == entry_id)


class AsyncCompilerAcceptanceTests(_AsyncCompilerBase):
    def test_async_byte_patch_script_is_accepted_with_marker(self):
        plan = self.compile(script_record(0, PATCH_SCRIPT, attributes='Async="1"'))
        entry = self.entry(plan)
        self.assertTrue(entry["supported"], entry["reason"])
        self.assertIs(entry["async"], True)
        self.assertEqual(len(entry["enable"]), 2)
        self.assertEqual(len(entry["disable"]), 2)
        self.assertIn("Async activation", entry["reason"])
        validate_plan(plan)

    def test_async_program_script_is_accepted_with_marker(self):
        plan = self.compile(script_record(0, PROGRAM_SCRIPT, attributes='Async="1"'))
        entry = self.entry(plan)
        self.assertTrue(entry["supported"], entry["reason"])
        self.assertIs(entry["async"], True)
        self.assertIn("program", entry)
        self.assertEqual(entry["enable"], [])
        self.assertIn("Async activation", entry["reason"])

    def test_async_lua_script_is_accepted_with_marker(self):
        plan = self.compile(script_record(0, LUA_SCRIPT, attributes='Async="1"'))
        entry = self.entry(plan)
        self.assertTrue(entry["supported"], entry["reason"])
        self.assertIs(entry["async"], True)
        self.assertIn("lua_program", entry)
        self.assertIn("Async activation", entry["reason"])

    def test_async_one_shot_script_is_accepted_with_marker(self):
        plan = self.compile(script_record(0, ONESHOT_SCRIPT, attributes='Async="1"'))
        entry = self.entry(plan)
        self.assertTrue(entry["supported"], entry["reason"])
        self.assertIs(entry["async"], True)
        self.assertIs(entry["one_shot"], True)
        self.assertEqual(len(entry["enable"]), 2)
        self.assertEqual(entry["disable"], [])
        self.assertIn("Async activation", entry["reason"])

    def test_async_marker_does_not_change_profile_selection(self):
        async_plan = self.compile(script_record(0, PATCH_SCRIPT, attributes='Async="1"')
                                  + script_record(1, PROGRAM_SCRIPT, attributes='Async="1"'))
        sync_plan = self.compile(script_record(0, PATCH_SCRIPT) + script_record(1, PROGRAM_SCRIPT))
        for async_entry, sync_entry in zip(async_plan["entries"], sync_plan["entries"]):
            self.assertEqual(async_entry["kind"], sync_entry["kind"])
            self.assertEqual(async_entry["supported"], sync_entry["supported"])
            self.assertEqual(async_entry.get("enable"), sync_entry.get("enable"))
            self.assertEqual(async_entry.get("disable"), sync_entry.get("disable"))
            self.assertEqual(async_entry.get("one_shot"), sync_entry.get("one_shot"))
            self.assertEqual(async_entry.get("program"), sync_entry.get("program"))

    def test_sync_scripts_carry_no_async_marker(self):
        plan = self.compile(script_record(0, PATCH_SCRIPT) + script_record(1, LUA_SCRIPT))
        for entry in plan["entries"]:
            self.assertNotIn("async", entry)

    def test_async_record_blocked_for_other_reason_keeps_no_marker(self):
        plan = self.compile(script_record(0, BLOCKED_SCRIPT, attributes='Async="1"'))
        entry = self.entry(plan)
        self.assertFalse(entry["supported"])
        self.assertIn("no executable patch or data", entry["reason"])
        self.assertNotIn("async", entry)
        self.assertNotIn("Async activation", entry["reason"])
        validate_plan(plan)

    def test_async_record_blocked_by_missing_symbol_keeps_no_marker(self):
        plan = self.compile(script_record(0, CONSUMER_SCRIPT, attributes='Async="1"'))
        entry = self.entry(plan)
        self.assertFalse(entry["supported"])
        self.assertIn("Required symbol", entry["reason"])
        self.assertNotIn("async", entry)
        validate_plan(plan)

    def test_async_record_pulls_symbol_provider_into_selection(self):
        plan = self.compile(script_record(0, LOCATOR_SCRIPT)
                            + script_record(1, CONSUMER_SCRIPT, attributes='Async="1"'),
                            selected_ids=[1])
        self.assertEqual(plan["selected_ids"], [0, 1])
        entry = self.entry(plan, 1)
        self.assertTrue(entry["supported"], entry["reason"])
        self.assertIs(entry["async"], True)
        self.assertEqual(entry["requires"], ["Anchor"])
        self.assertEqual(entry["dependency_ids"], [0])

    def test_async_plan_is_deterministic(self):
        body = (script_record(0, PATCH_SCRIPT, attributes='Async="1"')
                + script_record(1, LUA_SCRIPT, attributes='Async="1"'))
        plan_one = self.compile(body)
        plan_two = self.compile(body)
        self.assertEqual(json.dumps(plan_one, sort_keys=True),
                         json.dumps(plan_two, sort_keys=True))


class AsyncPlanValidationTests(_AsyncCompilerBase):
    def test_validation_rejects_false_async_marker(self):
        plan = self.compile(script_record(0, PATCH_SCRIPT, attributes='Async="1"'))
        plan["entries"][0]["async"] = False
        with self.assertRaises(NativeCompileError):
            validate_plan(plan)

    def test_validation_rejects_non_boolean_async_marker(self):
        plan = self.compile(script_record(0, PATCH_SCRIPT, attributes='Async="1"'))
        plan["entries"][0]["async"] = "yes"
        with self.assertRaises(NativeCompileError):
            validate_plan(plan)

    def test_validation_rejects_async_marker_on_value_entry(self):
        plan = self.compile(value_record(0, "Target.exe+10")
                            + script_record(1, PATCH_SCRIPT, attributes='Async="1"'))
        plan["entries"][0]["async"] = True
        with self.assertRaises(NativeCompileError):
            validate_plan(plan)

    def test_validation_rejects_async_marker_on_blocked_entry(self):
        plan = self.compile(script_record(0, BLOCKED_SCRIPT, attributes='Async="1"')
                            + script_record(1, PATCH_SCRIPT, attributes='Async="1"'))
        blocked = next(entry for entry in plan["entries"] if not entry["supported"])
        blocked["async"] = True
        with self.assertRaises(NativeCompileError):
            validate_plan(plan)

    def test_runtime_validation_accepts_async_marker(self):
        plan = self.compile(script_record(0, PATCH_SCRIPT, attributes='Async="1"'))
        self.assertIs(self.entry(plan)["async"], True)
        validate_runtime_plan(plan)


class AsyncEngineLifecycleTests(unittest.TestCase):
    """Slice B: the engine routes async records through the tested
    ActivationController.

    Attach gating, ownership, safety holds and the save boundary are enforced
    by the controller. The desired set (state.json) is the cross-session wish
    store: confirmed ON wishes replay on the next attach, and a failed attempt
    never persists as a wish (One-Shot save-boundary parity).
    """

    def setUp(self):
        from test_native_engine import FIXTURE, FakeMemory
        from ct2trainer.native.compiler import compile_table

        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.shared = self.directory / "shared"
        self.plan = compile_table(FIXTURE, "FixtureTarget.exe")
        self.memory = FakeMemory()
        self.original_data = bytes(self.memory.data)
        self.factory = lambda _name: self.memory
        self.engine = None

    def tearDown(self):
        if self.engine is not None and not self.engine.closed:
            self.engine.close()

    def make_async(self, entry_id: int) -> None:
        for entry in self.plan["entries"]:
            if entry["id"] == entry_id:
                entry["async"] = True

    def start(self, attach: bool = True):
        from ct2trainer.native.engine import TrainerEngine
        self.engine = TrainerEngine(self.plan, self.directory, self.factory, self.shared)
        if attach:
            self.engine.poll()
            self.assertTrue(self.engine.connected, self.engine.status)
        return self.engine

    def test_sync_plan_builds_no_async_controller(self):
        from ct2trainer.native.engine import NativeRuntimeError
        engine = self.start(False)
        self.assertIsNone(engine.async_policy)
        self.assertEqual(engine._async_ids, set())
        with self.assertRaisesRegex(NativeRuntimeError, "no async lifecycle"):
            engine.async_query(1)

    def test_async_plan_builds_controller_table(self):
        from ct2trainer.native.activation_policy import UnknownRecordError
        from ct2trainer.native.engine import NativeRuntimeError
        self.make_async(1)
        engine = self.start(False)
        self.assertIsNotNone(engine.async_policy)
        self.assertEqual(engine._async_ids, {1})
        state = engine.async_query(1)
        self.assertFalse(state["active"])
        self.assertFalse(state["hold"])
        self.assertFalse(state["saved_wish"])
        # Plan entry IDs start at zero; controller record IDs are offset by one.
        with self.assertRaises(UnknownRecordError):
            engine.async_policy.query(5)
        # Sync script entries inside the plan are not async lifecycle entries.
        with self.assertRaisesRegex(NativeRuntimeError, "no async lifecycle"):
            engine.async_query(0)

    def test_async_toggle_before_attach_is_refused(self):
        from ct2trainer.native.engine import NativeRuntimeError
        self.make_async(1)
        engine = self.start(False)
        with self.assertRaisesRegex(NativeRuntimeError, "not connected"):
            engine.toggle(1, True)
        self.assertNotIn(1, engine.desired)

    def test_async_toggle_on_confirms_and_saves_wish(self):
        self.make_async(1)
        engine = self.start()
        engine.toggle(1, True)
        self.assertEqual(self.memory.read(0x1014, 4), b"\1\0\0\0")
        self.assertEqual(engine.desired, {0, 1})
        self.assertEqual(set(engine.applied), {0, 1})
        state = engine.async_query(1)
        self.assertTrue(state["active"])
        self.assertTrue(state["saved_wish"])
        self.assertFalse(state["hold"])
        self.assertTrue(engine.close())
        self.assertEqual(engine.desired, {0, 1})

    def test_async_toggle_off_confirms_and_clears_wish(self):
        self.make_async(1)
        engine = self.start()
        engine.toggle(1, True)
        engine.toggle(1, False)
        self.assertEqual(self.memory.read(0x1014, 4), bytes(4))
        self.assertNotIn(1, engine.desired)
        self.assertNotIn(1, engine.applied)
        state = engine.async_query(1)
        self.assertFalse(state["active"])
        self.assertFalse(state["saved_wish"])
        self.assertFalse(state["hold"])

    def test_async_failed_assert_not_saved_and_retryable(self):
        from ct2trainer.native.engine import NativeRuntimeError
        self.make_async(1)
        engine = self.start()
        self.memory.data[20] = 8
        with self.assertRaisesRegex(NativeRuntimeError, "assertion"):
            engine.toggle(1, True)
        self.assertNotIn(1, engine.desired)
        self.assertNotIn(1, engine.applied)
        state = engine.async_query(1)
        self.assertFalse(state["active"])
        self.assertFalse(state["saved_wish"])
        self.assertFalse(state["hold"])
        self.assertFalse(engine.blocked)
        self.assertEqual(self.memory.writes, [])
        # Explicit retry after the target state is valid again succeeds.
        self.memory.data[20] = 0
        engine.toggle(1, True)
        self.assertIn(1, engine.desired)
        self.assertTrue(engine.async_query(1)["active"])

    def test_async_partial_write_rolls_back_without_hold(self):
        from ct2trainer.native.engine import NativeRuntimeError
        self.make_async(1)
        engine = self.start()
        self.memory.fail_once = True
        with self.assertRaisesRegex(NativeRuntimeError, "original bytes restored"):
            engine.toggle(1, True)
        self.assertEqual(self.memory.read(0x1014, 4), bytes(4))
        self.assertNotIn(1, engine.desired)
        self.assertFalse(engine.async_query(1)["hold"])
        engine.toggle(1, True)
        self.assertIn(1, engine.desired)
        self.assertTrue(engine.async_query(1)["active"])

    def test_async_partial_effect_triggers_safety_hold(self):
        from ct2trainer.native.engine import NativeRuntimeError
        self.make_async(1)
        engine = self.start()

        original_dispatch = engine._enable_dispatch

        def broken_dispatch(entry, persist):
            if entry["id"] != 1:
                original_dispatch(entry, persist)
                return
            # The effect lands in the target before the attempt fails.
            self.memory.write(0x1014, b"\1\0\0\0")
            raise NativeRuntimeError("injected partial async effect")

        engine._enable_dispatch = broken_dispatch
        with self.assertRaisesRegex(NativeRuntimeError, "injected partial"):
            engine.toggle(1, True)
        state = engine.async_query(1)
        self.assertFalse(state["active"])
        self.assertTrue(state["hold"])
        self.assertFalse(state["saved_wish"])
        self.assertNotIn(1, engine.desired)
        # A held record is refused without manual intervention.
        with self.assertRaisesRegex(NativeRuntimeError, "safety hold"):
            engine.toggle(1, True)

    def test_async_wish_replayed_after_controller_restart(self):
        from ct2trainer.native.engine import TrainerEngine
        self.make_async(1)
        engine = self.start()
        engine.toggle(1, True)
        self.assertTrue(engine.close())
        self.assertEqual(engine.desired, {0, 1})
        engine2 = TrainerEngine(self.plan, self.directory, self.factory, self.shared)
        self.engine = engine2
        engine2.poll()
        self.assertTrue(engine2.connected, engine2.status)
        self.assertIn(1, engine2.applied)
        self.assertEqual(self.memory.read(0x1014, 4), b"\1\0\0\0")
        state = engine2.async_query(1)
        self.assertTrue(state["active"])
        self.assertTrue(state["saved_wish"])

    def test_async_failed_attempt_not_replayed_after_restart(self):
        from ct2trainer.native.engine import NativeRuntimeError, TrainerEngine
        self.make_async(1)
        engine = self.start()
        self.memory.data[20] = 8
        with self.assertRaisesRegex(NativeRuntimeError, "assertion"):
            engine.toggle(1, True)
        # Restore the artificial target condition; the trainer wrote nothing.
        self.memory.data[20] = 0
        self.assertTrue(engine.close())
        engine2 = TrainerEngine(self.plan, self.directory, self.factory, self.shared)
        self.engine = engine2
        engine2.poll()
        self.assertTrue(engine2.connected, engine2.status)
        self.assertNotIn(1, engine2.applied)
        self.assertNotIn(1, engine2.desired)
        self.assertEqual(self.memory.read(0x1014, 4), bytes(4))

    def test_detach_drains_async_state_and_keeps_saved_wishes(self):
        self.make_async(1)
        engine = self.start()
        engine.toggle(1, True)
        self.assertTrue(engine.async_query(1)["active"])
        self.memory.alive = False
        engine.poll()
        self.assertFalse(engine.connected)
        self.assertEqual(engine.desired, {0, 1})
        self.assertNotIn(1, engine.applied)
        # Simulate a fresh target process: original bytes, new liveness.
        self.memory.data[:] = self.original_data
        self.memory.alive = True
        # Re-attach replays the confirmed wish through the controller.
        engine.poll()
        self.assertTrue(engine.connected, engine.status)
        self.assertIn(1, engine.applied)
        state = engine.async_query(1)
        self.assertTrue(state["active"])
        self.assertTrue(state["saved_wish"])

    def test_async_auto_on_pending_wish_fulfilled_on_attach(self):
        self.make_async(1)
        engine = self.start(False)
        engine.request_auto_on(1)
        self.assertIn(1, engine.desired)
        engine.poll()
        self.assertTrue(engine.connected, engine.status)
        self.assertIn(1, engine.applied)
        state = engine.async_query(1)
        self.assertTrue(state["active"])
        self.assertTrue(state["saved_wish"])

    def test_async_reeenable_is_idempotent(self):
        self.make_async(1)
        engine = self.start()
        engine.toggle(1, True)
        engine.toggle(1, True)
        self.assertEqual(self.memory.read(0x1014, 4), b"\1\0\0\0")
        self.assertEqual(engine.desired, {0, 1})
        self.assertTrue(engine.async_query(1)["active"])

    def test_malformed_async_marker_on_value_entry_refused_by_engine(self):
        from ct2trainer.native.engine import NativeRuntimeError
        for entry in self.plan["entries"]:
            if entry["id"] == 2:
                entry["async"] = True
        with self.assertRaises(NativeRuntimeError):
            self.start(False)

    def test_save_wish_guard_requires_confirmed_on(self):
        from ct2trainer.native.activation_policy import WishSaveRefused
        self.make_async(1)
        engine = self.start(False)
        with self.assertRaises(WishSaveRefused):
            engine.async_policy.save_wish(2)


if __name__ == "__main__":
    unittest.main()
