"""Typed target call wiring (N-14): executeCodeEx through the call broker.

Pinned corpus shape (case-08, origin: Clair Obscure Expedition 33,
record "Add XP +?"):

    local func = executeCodeEx(0,nil,Find,0,readPointer(Data+0x10),
                               {type = 4,value = "AddExperience"},1)
    executeCodeEx(0,nil,process,Data,func,p)

This file proves the full chain on own synthetic fixtures: CT Lua script ->
compiled plan -> engine attach (injected call-broker binding created) ->
record activation -> executeCodeEx in the ENABLE phase -> tested CallBroker
submit/wait -> typed result returned to the Lua side. Fail-closed refusals
(no backend, target not attached, closed engine, contract mismatches,
target refusal, lost ack, busy session) are asserted with no side effects.
Real live-target execution stays open (AP-11 binary gates).
"""
from __future__ import annotations

import json
import struct
import tempfile
import unittest
from pathlib import Path

from test_native_call_broker import PE_SHA, ScriptedTransport
from test_native_engine_code import Coordinator
from test_native_lua_activation import Memory
from ct2trainer.native.call_broker import (ArgValue, CallBroker,
                                             ImageIdentity, ReceiptStatus)
from ct2trainer.native.compiler import compile_table
from ct2trainer.native.engine import (NativeRuntimeError, TrainerEngine,
                                       validate_plan)
from ct2trainer.native.lua_host import LuaHostError
from ct2trainer.native.target_broker import (CallContext, Frame,
                                               ReceiptJournal, TypedBroker)
from ct2trainer.native.target_broker.protocol import Command, Operation
from ct2trainer.native.typed_call import (TypedCallBusy,
                                            TypedCallContractError,
                                            TypedCallNotAttached,
                                            TypedCallRefused,
                                            TypedCallUncertain,
                                            execute_code_ex)

CT_BODY = '''<CheatTable CheatEngineTableVersion="45"><CheatEntries>
<CheatEntry><ID>3000</ID><Description>"Add XP +?"</Description><VariableType>Auto Assembler Script</VariableType><AssemblerScript>{$lua}
if syntaxcheck then return end

[ENABLE]
local process = getAddress("ProcessEvent")
local Find = getAddress("aobStaticFind")
local Data = 0x1020
local payload = readPointer(Data + 8)
local func = executeCodeEx(0,nil,Find,0,payload)
executeCodeEx(0,nil,process,func,Data)

[DISABLE]

</AssemblerScript></CheatEntry>
<CheatEntry><ID>3010</ID><Description>"Process Symbol"</Description><VariableType>Auto Assembler Script</VariableType><AssemblerScript>[ENABLE]
define(ProcessEvent,1030)
assert(ProcessEvent,00)
registersymbol(ProcessEvent)
[DISABLE]
unregistersymbol(ProcessEvent)
</AssemblerScript></CheatEntry>
<CheatEntry><ID>3020</ID><Description>"Find Symbol"</Description><VariableType>Auto Assembler Script</VariableType><AssemblerScript>[ENABLE]
define(aobStaticFind,1040)
assert(aobStaticFind,00)
registersymbol(aobStaticFind)
[DISABLE]
unregistersymbol(aobStaticFind)
</AssemblerScript></CheatEntry>
</CheatEntries></CheatTable>'''


def make_broker(directory: Path, **transport_kwargs):
    """Scripted-transport CallBroker session pinned to target identity (3,4)."""
    journal = ReceiptJournal(directory, {"owner": [1, 2], "target": [3, 4]})
    transport = ScriptedTransport(**transport_kwargs)
    broker = TypedBroker(
        Frame(Command.HELLO, owner_pid=1, owner_created=2, target_pid=3,
              target_created=4, nonce=b"x" * 16),
        transport, journal, lambda: 1000, 1000000)
    broker.handshake(CallContext.seconds(1))
    image = ImageIdentity(pid=3, created_filetime=4, pe_sha256=PE_SHA)
    return CallBroker(broker, image), broker, transport, journal


def journal_kinds(journal) -> list:
    return [json.loads(path.read_bytes())["kind"]
            for path in sorted(journal.directory.glob("*.json"))]


class TypedCallContractTests(unittest.TestCase):
    """executeCodeEx contract layer over a scripted fixture broker."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.cb, self.broker, self.transport, self.journal = make_broker(
            Path(self.temporary.name) / "broker", complete_after_queries=1)

    def _no_side_effects(self) -> None:
        self.assertEqual(self.transport.submissions, [])
        self.assertEqual(self.transport.calls, 0)
        self.assertEqual(self.cb.receipts, {})

    def test_two_word_call_completes_with_typed_result_and_receipt(self):
        result = execute_code_ex(self.cb, (0, None, 0x401000, 2, 3))
        self.assertEqual(result, 5)
        self.assertEqual(self.transport.calls, 1)
        submission = self.transport.submissions[0]
        self.assertEqual(submission.operation, int(Operation.CDECL_ADD))
        self.assertEqual(submission.payload, struct.pack("<ii", 2, 3))
        receipt = list(self.cb.receipts.values())[0]
        self.assertEqual(receipt.status, ReceiptStatus.DONE)
        self.assertEqual(receipt.result, 5)
        self.assertTrue(receipt.terminal)
        self.assertFalse(self.broker.uncertain)
        self.assertIn('call-receipt', journal_kinds(self.journal))

    def test_first_result_feeds_the_second_call_like_the_corpus(self):
        func = execute_code_ex(self.cb, (0, None, 0x401000, 0, 42))
        self.assertEqual(func, 5)
        execute_code_ex(self.cb, (0, None, 0x402000, func, 0x1000))
        self.assertEqual(self.transport.calls, 2)
        self.assertEqual(self.transport.submissions[1].payload,
                         struct.pack("<ii", 5, 0x1000))
        self.assertEqual(set(self.cb.entries), {"fn-401000", "fn-402000"})

    def test_same_function_rebinds_idempotently(self):
        first = execute_code_ex(self.cb, (0, None, 0x401000, 1, 2))
        again = execute_code_ex(self.cb, (0, None, 0x401000, 1, 2))
        self.assertEqual((first, again), (5, 5))
        self.assertEqual(len(self.cb.entries), 1)
        self.assertEqual(len(self.transport.submissions), 2)

    def test_call_shape_refusals_are_named_and_side_effect_free(self):
        cases = [
            ("too few arguments", (0, None, 0x401000)),
            ("nonzero handle", (1, None, 0x401000, 1, 2)),
            ("non-nil reserved slot", (0, 0, 0x401000, 1, 2)),
            ("zero function address", (0, None, 0, 1, 2)),
            ("negative function address", (0, None, -8, 1, 2)),
            ("non-address function", (0, None, "0x401000", 1, 2)),
            ("one word", (0, None, 0x401000, 1)),
            ("three words", (0, None, 0x401000, 1, 2, 3)),
            ("six words", (0, None, 0x401000, 1, 2, 3, 4, 5, 6)),
            ("string word", (0, None, 0x401000, 1, "x")),
            ("float word", (0, None, 0x401000, 1, 2.5)),
            ("boolean word", (0, None, 0x401000, 1, True)),
        ]
        for label, arguments in cases:
            with self.subTest(label=label):
                with self.assertRaises(TypedCallContractError):
                    execute_code_ex(self.cb, arguments)
                self._no_side_effects()

    def test_word_outside_the_int32_wire_slot_is_refused(self):
        with self.assertRaises(TypedCallContractError):
            execute_code_ex(self.cb, (0, None, 0x401000, 2 ** 31, 3))
        self._no_side_effects()

    def test_argument_container_must_be_a_list_or_tuple(self):
        with self.assertRaises(TypedCallContractError):
            execute_code_ex(self.cb, {"0": 0, "nil": None, "fn": 0x401000})
        self._no_side_effects()

    def test_outstanding_call_makes_the_route_busy(self):
        call = self.cb.marshal(
            Operation.CDECL_ADD, (ArgValue(1), ArgValue(2)))
        self.cb.submit(call, CallContext.seconds(1), hold_start=True)
        with self.assertRaises(TypedCallBusy):
            execute_code_ex(self.cb, (0, None, 0x401000, 4, 5))
        self.assertEqual(len(self.transport.submissions), 1)
        self.assertEqual(self.transport.calls, 0)

    def test_target_refusal_is_named_with_the_error_code(self):
        self.transport.refuse_submit = True
        with self.assertRaisesRegex(TypedCallRefused, "error 1460"):
            execute_code_ex(self.cb, (0, None, 0x401000, 1, 2))
        receipt = list(self.cb.receipts.values())[0]
        self.assertEqual(receipt.status, ReceiptStatus.REFUSED)
        self.assertEqual(receipt.error, 1460)
        self.assertTrue(receipt.terminal)

    def test_lost_ack_is_terminal_uncertain_and_blocks_retry(self):
        self.transport.drop_ack = True
        with self.assertRaises(TypedCallUncertain):
            execute_code_ex(self.cb, (0, None, 0x401000, 1, 2))
        with self.assertRaises(TypedCallUncertain):
            execute_code_ex(self.cb, (0, None, 0x401000, 1, 2))
        self.assertEqual(len(self.transport.submissions), 1)
        self.assertTrue(self.broker.uncertain)

    def test_unknown_target_state_is_terminal_uncertain(self):
        self.transport.unknown_on_query = True
        with self.assertRaises(TypedCallUncertain):
            execute_code_ex(self.cb, (0, None, 0x401000, 1, 2))
        self.assertTrue(self.broker.uncertain)

    def test_closed_broker_session_is_refused(self):
        self.cb.close()
        with self.assertRaises(TypedCallNotAttached):
            execute_code_ex(self.cb, (0, None, 0x401000, 1, 2))

    def test_missing_or_foreign_broker_is_refused(self):
        with self.assertRaises(TypedCallNotAttached):
            execute_code_ex(None, (0, None, 0x401000, 1, 2))
        with self.assertRaises(TypedCallNotAttached):
            execute_code_ex("nope", (0, None, 0x401000, 1, 2))


class TypedCallEngineLifecycleTests(unittest.TestCase):
    """Engine-owned binding: created at attach, fresh per attach, gone on exit."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "table.ct").write_text(CT_BODY, encoding="utf-8")
        self.memory = Memory(pid=3, creation_time=4)
        self.memory.data[0x28:0x30] = struct.pack("<Q", 42)
        self.brokers = []

    def factory(self, engine, memory):
        call_broker, broker, transport, journal = make_broker(
            self.root / f"broker-{len(self.brokers)}", complete_after_queries=1)
        self.brokers.append((call_broker, broker, transport, journal))
        return call_broker

    def make_engine(self, **extra):
        return TrainerEngine(compile_table(self.root / "table.ct", "FixtureTarget.exe"),
                             state_dir=self.root / "state",
                             process_lock_dir=self.root / "shared",
                             memory_factory=lambda name: self.memory,
                             hook_coordinator=Coordinator(),
                             **extra)

    def tearDown(self):
        if getattr(self, "engine", None) is not None and not self.engine.closed:
            self.memory.alive = False
            self.engine.poll()
            self.engine.close()

    def test_binding_created_at_attach_and_fresh_after_re_attach(self):
        self.engine = self.make_engine(call_broker_factory=self.factory)
        self.engine.poll()
        self.assertTrue(self.engine.connected, self.engine.status)
        self.assertIs(self.engine.call_broker, self.brokers[0][0])
        # Confirmed target exit invalidates the binding; the receipt journal
        # keeps the durable close evidence.
        self.memory.alive = False
        self.engine.poll()
        self.assertIsNone(self.engine.call_broker)
        self.assertTrue(self.brokers[0][1].closed)
        self.assertIn("call-close", journal_kinds(self.brokers[0][3]))
        # Re-attach creates a fresh binding, never the retired one.
        self.memory.alive = True
        self.engine.poll()
        self.assertTrue(self.engine.connected, self.engine.status)
        self.assertEqual(len(self.brokers), 2)
        self.assertIs(self.engine.call_broker, self.brokers[1][0])
        self.assertFalse(self.brokers[1][1].closed)

    def test_binding_is_released_on_engine_close(self):
        self.engine = self.make_engine(call_broker_factory=self.factory)
        self.engine.poll()
        self.assertTrue(self.engine.close())
        self.assertIsNone(self.engine.call_broker)
        self.assertTrue(self.brokers[0][1].closed)
        self.assertIn("call-close", journal_kinds(self.brokers[0][3]))

    def test_factory_failure_keeps_the_trainer_waiting(self):
        attempts = 0

        def flaky_factory(engine, memory):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("pipe missing")
            return self.factory(engine, memory)

        self.engine = self.make_engine(call_broker_factory=flaky_factory)
        self.engine.poll()
        self.assertFalse(self.engine.connected)
        self.assertIn("call broker unavailable", self.engine.status)
        self.assertTrue(self.memory.closed)
        self.assertFalse((self.root / "state" / "session.json").exists())
        self.assertFalse((self.root / "shared" / "3-4.json").exists())
        self.engine.poll()
        self.assertTrue(self.engine.connected, self.engine.status)
        self.assertEqual(attempts, 2)
        self.assertIs(self.engine.call_broker, self.brokers[0][0])

    def test_mismatched_broker_identity_refuses_attach(self):
        def mismatched_factory(engine, memory):
            foreign = TypedBroker(
                Frame(Command.HELLO, owner_pid=1, owner_created=2, target_pid=9,
                      target_created=4, nonce=b"x" * 16),
                ScriptedTransport(),
                ReceiptJournal(self.root / "broker-bad-journal",
                               {"owner": [1, 2], "target": [9, 4]}),
                lambda: 1000, 1000000)
            foreign.handshake(CallContext.seconds(1))
            return CallBroker(foreign,
                              ImageIdentity(pid=9, created_filetime=4,
                                            pe_sha256=PE_SHA))

        self.engine = self.make_engine(call_broker_factory=mismatched_factory)
        self.engine.poll()
        self.assertFalse(self.engine.connected)
        self.assertIn("call broker unavailable", self.engine.status)
        self.assertTrue(self.memory.closed)

    def test_typed_call_refused_before_attach(self):
        self.engine = self.make_engine(call_broker_factory=self.factory)
        with self.assertRaisesRegex(TypedCallNotAttached, "not connected"):
            self.engine.typed_call((0, None, 0x1040, 1, 2))
        self.engine.poll()
        self.assertTrue(self.engine.connected, self.engine.status)
        # Confirmed exit retires the binding as well.
        self.memory.alive = False
        self.engine.poll()
        with self.assertRaisesRegex(TypedCallNotAttached, "not connected"):
            self.engine.typed_call((0, None, 0x1040, 1, 2))
        self.assertIsNone(self.engine.call_broker)

    def test_typed_call_refused_without_configured_backend(self):
        self.engine = self.make_engine()
        self.engine.poll()
        self.assertTrue(self.engine.connected, self.engine.status)
        with self.assertRaisesRegex(TypedCallNotAttached, "No call-broker binding"):
            self.engine.typed_call((0, None, 0x1040, 1, 2))
        self.assertIsNone(self.engine.call_broker)

    def test_typed_call_after_close_is_refused(self):
        self.engine = self.make_engine(call_broker_factory=self.factory)
        self.engine.poll()
        self.assertTrue(self.engine.close())
        with self.assertRaisesRegex(TypedCallNotAttached, "closed"):
            self.engine.typed_call((0, None, 0x1040, 1, 2))

    def test_typed_call_routes_through_the_bound_broker(self):
        self.engine = self.make_engine(call_broker_factory=self.factory)
        self.engine.poll()
        result = self.engine.typed_call((0, None, 0x1040, 0, 42))
        self.assertEqual(result, 5)
        self.assertEqual(self.brokers[0][2].calls, 1)
        self.assertEqual(self.brokers[0][2].submissions[0].payload,
                         struct.pack("<ii", 0, 42))
        self.assertIn("fn-1040", self.brokers[0][0].entries)


class TypedCallLuaChainTests(TypedCallEngineLifecycleTests):
    """CT Lua script -> plan -> engine -> Lua host -> executeCodeEx -> broker."""

    def test_plan_carries_the_corpus_shaped_lua_record(self):
        plan = compile_table(self.root / "table.ct", "FixtureTarget.exe")
        by_id = {entry["id"]: entry for entry in plan["entries"]}
        self.assertEqual(by_id[3000]["kind"], "script")
        self.assertTrue(by_id[3000]["supported"])
        self.assertFalse(by_id[3000].get("one_shot"))
        self.assertIn("executeCodeEx", by_id[3000]["lua_program"]["source"])
        # The typed call is a runtime API: it never appears in plan metadata.
        self.assertEqual(by_id[3000]["lua_program"]["requires"], [])
        self.assertEqual(by_id[3000]["requires"], [])
        validate_plan(plan)

    def test_corpus_shaped_enable_executes_both_typed_calls(self):
        self.engine = self.make_engine(call_broker_factory=self.factory)
        self.engine.poll()
        self.assertTrue(self.engine.connected, self.engine.status)
        self.assertTrue(self.engine.toggle(3010, True), self.engine.error)
        self.assertTrue(self.engine.toggle(3020, True), self.engine.error)
        self.assertTrue(self.engine.toggle(3000, True), self.engine.error)
        call_broker, _broker, transport, journal = self.brokers[0]
        self.assertEqual(len(transport.submissions), 2)
        self.assertEqual(transport.calls, 2)
        self.assertEqual(transport.submissions[0].operation,
                         int(Operation.CDECL_ADD))
        self.assertEqual(transport.submissions[0].payload,
                         struct.pack("<ii", 0, 42))
        self.assertEqual(transport.submissions[1].payload,
                         struct.pack("<ii", 5, 0x1020))
        self.assertEqual(call_broker.entries["fn-1040"].address, 0x1040)
        self.assertEqual(call_broker.entries["fn-1030"].address, 0x1030)
        receipts = sorted(call_broker.receipts.values(),
                          key=lambda receipt: receipt.request_id)
        self.assertEqual([receipt.status for receipt in receipts],
                         [ReceiptStatus.DONE, ReceiptStatus.DONE])
        self.assertEqual([receipt.result for receipt in receipts], [5, 5])
        kinds = journal_kinds(journal)
        for kind in ("call-session", "call-entry", "call-intent",
                     "call-submitted", "call-receipt"):
            self.assertIn(kind, kinds)
        journal.verify()
        self.assertEqual(self.memory.writes, [],
                         "typed calls must not write fixture memory")
        self.assertIn("processevent", self.engine.symbols)
        self.assertIn("aobstaticfind", self.engine.symbols)

    def test_disable_roundtrip_is_call_free_and_reversible(self):
        self.engine = self.make_engine(call_broker_factory=self.factory)
        self.engine.poll()
        self.assertTrue(self.engine.toggle(3010, True), self.engine.error)
        self.assertTrue(self.engine.toggle(3020, True), self.engine.error)
        self.assertTrue(self.engine.toggle(3000, True), self.engine.error)
        transport = self.brokers[0][2]
        self.assertEqual(transport.calls, 2)
        self.assertFalse(self.engine.toggle(3000, False))
        self.assertNotIn(3000, self.engine.applied)
        self.assertNotIn(3000, self.engine.lua_activations)
        self.assertEqual(transport.calls, 2,
                         "the empty [DISABLE] phase issues no calls")
        self.assertTrue(self.engine.toggle(3000, True), self.engine.error)
        self.assertEqual(transport.calls, 4)

    def test_failed_typed_call_fails_enable_and_saves_nothing(self):
        def refusing_factory(engine, memory):
            call_broker, broker, transport, journal = make_broker(
                self.root / "broker-refused", complete_after_queries=1,
                refuse_submit=True)
            self.brokers.append((call_broker, broker, transport, journal))
            return call_broker

        self.engine = self.make_engine(call_broker_factory=refusing_factory)
        self.engine.poll()
        self.assertTrue(self.engine.toggle(3010, True), self.engine.error)
        self.assertTrue(self.engine.toggle(3020, True), self.engine.error)
        with self.assertRaises(NativeRuntimeError):
            self.engine.toggle(3000, True)
        self.assertNotIn(3000, self.engine.applied)
        self.assertNotIn(3000, self.engine.lua_activations)
        self.assertNotIn(3000, self.engine.desired,
                         "a failed enable must not save a wish")
        self.assertFalse(self.engine.blocked, self.engine.error)
        call_broker, broker, transport, journal = self.brokers[0]
        self.assertEqual(transport.calls, 0)
        receipt = list(call_broker.receipts.values())[0]
        self.assertEqual(receipt.status, ReceiptStatus.REFUSED)
        self.assertEqual(receipt.error, 1460)
        self.assertIn("call-receipt", journal_kinds(journal))

    def test_without_backend_the_record_stays_fail_closed(self):
        self.engine = self.make_engine()
        self.engine.poll()
        self.assertTrue(self.engine.toggle(3010, True), self.engine.error)
        self.assertTrue(self.engine.toggle(3020, True), self.engine.error)
        with self.assertRaises(NativeRuntimeError):
            self.engine.toggle(3000, True)
        self.assertNotIn(3000, self.engine.applied)
        self.assertNotIn(3000, self.engine.desired)

    def test_syntaxcheck_and_helper_bootstrap_refuse_typed_calls(self):
        self.engine = self.make_engine(call_broker_factory=self.factory)
        self.engine.poll()
        host = self.engine.open_lua_session()
        with self.assertRaisesRegex(LuaHostError, "mutation API"):
            host.execute("executeCodeEx(0,nil,0x1040,1,2)", syntaxcheck=True)
        with self.assertRaisesRegex(LuaHostError, "mutation API"):
            host.install_helpers("executeCodeEx(0,nil,1,2,3)")
        self.assertEqual(self.brokers[0][2].calls, 0)
        self.assertEqual(self.brokers[0][2].submissions, [])


if __name__ == "__main__":
    unittest.main()
